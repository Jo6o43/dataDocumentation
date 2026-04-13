import sys
import json
import threading
import time
import ctypes
from pathlib import Path
from datetime import datetime
import pygame

try:
	import inputs
except ImportError:
	inputs = None


WINDOW_WIDTH = 700
WINDOW_HEIGHT = 520
FPS = 60
DEADZONE = 0.15
OUTPUT_FILE = "right_stick_outputs.json"
HISTORY_DOT_COUNT = 40
OUTPUT_DIR = Path("controllerTracker_outputs")
POLL_INTERVAL_SECONDS = 0.001


class XINPUT_GAMEPAD(ctypes.Structure):
	_fields_ = [
		("wButtons", ctypes.c_ushort),
		("bLeftTrigger", ctypes.c_ubyte),
		("bRightTrigger", ctypes.c_ubyte),
		("sThumbLX", ctypes.c_short),
		("sThumbLY", ctypes.c_short),
		("sThumbRX", ctypes.c_short),
		("sThumbRY", ctypes.c_short),
	]


class XINPUT_STATE(ctypes.Structure):
	_fields_ = [
		("dwPacketNumber", ctypes.c_ulong),
		("Gamepad", XINPUT_GAMEPAD),
	]


def load_xinput_library():
	for dll_name in ["xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"]:
		try:
			return ctypes.WinDLL(dll_name)
		except OSError:
			continue
	return None


def normalize_stick_axis(raw_value):
	if raw_value >= 0:
		return raw_value / 32767.0
	return raw_value / 32768.0


def clamp(value, min_value, max_value):
	return max(min_value, min(max_value, value))


def apply_deadzone(value, deadzone):
	if abs(value) < deadzone:
		return 0.0
	sign = 1.0 if value >= 0 else -1.0
	return sign * ((abs(value) - deadzone) / (1.0 - deadzone))


def draw_centered_text(surface, text, font, color, y):
	rendered = font.render(text, True, color)
	rect = rendered.get_rect(center=(WINDOW_WIDTH // 2, y))
	surface.blit(rendered, rect)


def save_outputs_to_json(path, output_rows):
	with open(path, "w", encoding="utf-8") as json_file:
		json.dump(output_rows, json_file, indent=2)


def get_unique_output_path(output_dir, base_filename):
	output_dir.mkdir(parents=True, exist_ok=True)
	base_path = output_dir / base_filename
	if not base_path.exists():
		return base_path

	stem = base_path.stem
	suffix = base_path.suffix
	index = 1
	while True:
		candidate = output_dir / f"{stem}_{index}{suffix}"
		if not candidate.exists():
			return candidate
		index += 1


class JoystickPoller:
	def __init__(self, output_path):
		self.output_path = output_path
		self.running = True
		self.current_x = 0.0
		self.current_y = 0.0
		self.previous_rounded = None
		self.output_rows = []
		self.history_points = []
		self.lock = threading.Lock()

		self.backend_name = "inputs"
		self.xinput_dll = load_xinput_library()
		if self.xinput_dll is not None:
			self.backend_name = "xinput"
			self.xinput_state = XINPUT_STATE()
			self.xinput_get_state = self.xinput_dll.XInputGetState
			self.xinput_get_state.argtypes = [ctypes.c_uint, ctypes.POINTER(XINPUT_STATE)]
			self.xinput_get_state.restype = ctypes.c_uint
		
		self.thread = threading.Thread(target=self._poll, daemon=True)
		self.thread.start()

	def _poll(self):
		while self.running:
			try:
				if self.backend_name == "xinput":
					self._poll_xinput()
				else:
					self._poll_inputs()
			except Exception:
				pass
			time.sleep(POLL_INTERVAL_SECONDS)

	def _poll_xinput(self):
		# Read from the first connected XInput controller.
		for user_index in range(4):
			result = self.xinput_get_state(user_index, ctypes.byref(self.xinput_state))
			if result == 0:
				raw_x = normalize_stick_axis(self.xinput_state.Gamepad.sThumbRX)
				raw_y = normalize_stick_axis(self.xinput_state.Gamepad.sThumbRY)
				with self.lock:
					self.current_x = clamp(raw_x, -1.0, 1.0)
					self.current_y = clamp(raw_y, -1.0, 1.0)
					self._check_and_save()
				return

		with self.lock:
			self.current_x = 0.0
			self.current_y = 0.0

	def _poll_inputs(self):
		if inputs is None:
			return

		events = inputs.get_gamepad()
		raw_x = None
		raw_y = None

		for event in events:
			if event.ev_type != "Absolute" or event.state is None:
				continue
			if event.code == "ABS_RX":
				raw_x = event.state / 32768.0
			elif event.code == "ABS_RY":
				raw_y = -event.state / 32768.0

		with self.lock:
			if raw_x is not None:
				self.current_x = clamp(raw_x, -1.0, 1.0)
			if raw_y is not None:
				self.current_y = clamp(raw_y, -1.0, 1.0)
			self._check_and_save()

	def _check_and_save(self):
		x = apply_deadzone(self.current_x, DEADZONE)
		y = apply_deadzone(self.current_y, DEADZONE)
		
		rounded_pair = (round(x, 3), round(y, 3))
		if rounded_pair != self.previous_rounded:
			timestamp = datetime.now().isoformat(timespec="milliseconds")
			output_entry = {
				"timestamp": timestamp,
				"x": rounded_pair[0],
				"y": rounded_pair[1],
			}
			self.output_rows.append(output_entry)
			self._save_json()

			self.history_points.append((rounded_pair[0], rounded_pair[1]))
			if len(self.history_points) > HISTORY_DOT_COUNT:
				self.history_points = self.history_points[-HISTORY_DOT_COUNT:]

			print(f"Right Stick -> X: {rounded_pair[0]: .3f} | Y: {rounded_pair[1]: .3f}")
			self.previous_rounded = rounded_pair

	def _save_json(self):
		with open(self.output_path, "w", encoding="utf-8") as json_file:
			json.dump(self.output_rows, json_file, indent=2)

	def get_state(self):
		with self.lock:
			return (
				apply_deadzone(self.current_x, DEADZONE),
				apply_deadzone(self.current_y, DEADZONE),
				list(self.history_points),
			)

	def stop(self):
		self.running = False
		self.thread.join(timeout=1.0)


def main():
	pygame.init()

	screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
	pygame.display.set_caption("Controller Right Stick Tracker")
	screen.set_alpha(255)
	clock = pygame.time.Clock()

	font_title = pygame.font.SysFont("consolas", 28, bold=True)
	font_body = pygame.font.SysFont("consolas", 22)
	font_small = pygame.font.SysFont("consolas", 18)

	print("Initializing low-latency input listener...")
	output_path = get_unique_output_path(OUTPUT_DIR, OUTPUT_FILE)
	print(f"Saving outputs to {output_path}")
	
	poller = JoystickPoller(output_path)
	print(f"Input backend: {poller.backend_name}")
	if poller.backend_name == "inputs":
		if inputs is None:
			print("No controller backend available.")
			print("Install 'inputs' or use an XInput-compatible controller.")
			poller.stop()
			pygame.quit()
			sys.exit(1)
		print("Fallback backend in use. For lowest latency, use an XInput controller.")
	time.sleep(0.5)
	
	running = True
	while running:
		pygame.event.pump()
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				running = False
			elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
				running = False

		x, y, history_points = poller.get_state()

		screen.fill((16, 18, 24))

		draw_centered_text(screen, "Right Stick Input", font_title, (235, 235, 235), 40)
		draw_centered_text(screen, "Controller Tracking (Background)", font_small, (185, 200, 220), 78)
		draw_centered_text(screen, "Works while playing other games", font_small, (160, 180, 200), 102)
		draw_centered_text(screen, f"X: {x: .3f}", font_body, (230, 200, 120), 145)
		draw_centered_text(screen, f"Y: {y: .3f}", font_body, (150, 210, 255), 178)
		draw_centered_text(screen, "Press ESC to quit", font_small, (150, 150, 150), 495)

		circle_size = 300
		circle_x = WINDOW_WIDTH // 2 - circle_size // 2
		circle_y = 200
		center_x = circle_x + circle_size // 2
		center_y = circle_y + circle_size // 2
		radius = circle_size // 2
		inner_radius = radius - 8

		pygame.draw.circle(screen, (90, 100, 120), (center_x, center_y), radius, width=2)
		pygame.draw.line(screen, (60, 70, 85), (center_x - radius, center_y), (center_x + radius, center_y), width=1)
		pygame.draw.line(screen, (60, 70, 85), (center_x, center_y - radius), (center_x, center_y + radius), width=1)

		for point_x, point_y in history_points[:-1]:
			history_dot_x = int(center_x + clamp(point_x, -1.0, 1.0) * inner_radius)
			history_dot_y = int(center_y + clamp(point_y, -1.0, 1.0) * inner_radius)
			pygame.draw.circle(screen, (220, 70, 70), (history_dot_x, history_dot_y), 4)

		dot_x = int(center_x + clamp(x, -1.0, 1.0) * inner_radius)
		dot_y = int(center_y + clamp(y, -1.0, 1.0) * inner_radius)
		pygame.draw.circle(screen, (255, 180, 100), (dot_x, dot_y), 8)

		pygame.display.flip()
		clock.tick(FPS)

	poller.stop()
	pygame.quit()
	sys.exit(0)


if __name__ == "__main__":
	main()
