import sys
import json
import threading
import time
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
PRIMARY_RIGHT_X_AXIS = "ABS_RX"
PRIMARY_RIGHT_Y_AXIS = "ABS_RY"
FALLBACK_RIGHT_X_AXIS = "ABS_Z"
FALLBACK_RIGHT_Y_AXIS = "ABS_RZ"


def clamp(value, min_value, max_value):
	return max(min_value, min(max_value, value))


def apply_deadzone(value, deadzone):
	if abs(value) < deadzone:
		return 0.0
	sign = 1.0 if value >= 0 else -1.0
	return sign * ((abs(value) - deadzone) / (1.0 - deadzone))


def pick_right_stick_axes(joystick):
	"""Pick a likely right-stick axis pair for common controller layouts."""
	axis_count = joystick.get_numaxes()
	common_pairs = [(2, 3), (3, 4)]
	for pair in common_pairs:
		if pair[0] < axis_count and pair[1] < axis_count:
			return pair

	if axis_count >= 4:
		return 2, 3
	if axis_count >= 2:
		return 0, 1
	return None


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
		
		self.axis_states = {
			PRIMARY_RIGHT_X_AXIS: 0.0,
			PRIMARY_RIGHT_Y_AXIS: 0.0,
			FALLBACK_RIGHT_X_AXIS: 0.0,
			FALLBACK_RIGHT_Y_AXIS: 0.0,
		}
		self.right_stick_x_axis = PRIMARY_RIGHT_X_AXIS
		self.right_stick_y_axis = PRIMARY_RIGHT_Y_AXIS
		
		self.thread = threading.Thread(target=self._poll, daemon=True)
		self.thread.start()

	def _poll(self):
		while self.running:
			try:
				events = inputs.get_gamepad()
				for event in events:
					if event.ev_type == 'Absolute' and event.state is not None:
						self.axis_states[event.code] = event.state / 32768.0

				self._select_axis_pair()
				
				with self.lock:
					raw_x = self.axis_states.get(self.right_stick_x_axis, 0.0)
					raw_y = self.axis_states.get(self.right_stick_y_axis, 0.0)

					self.current_x = clamp(raw_x, -1.0, 1.0)
					self.current_y = clamp(-raw_y, -1.0, 1.0)

					self._check_and_save()
			except Exception:
				pass
			time.sleep(0.001)

	def _select_axis_pair(self):
		if PRIMARY_RIGHT_X_AXIS in self.axis_states and PRIMARY_RIGHT_Y_AXIS in self.axis_states:
			self.right_stick_x_axis = PRIMARY_RIGHT_X_AXIS
			self.right_stick_y_axis = PRIMARY_RIGHT_Y_AXIS
		elif FALLBACK_RIGHT_X_AXIS in self.axis_states and FALLBACK_RIGHT_Y_AXIS in self.axis_states:
			self.right_stick_x_axis = FALLBACK_RIGHT_X_AXIS
			self.right_stick_y_axis = FALLBACK_RIGHT_Y_AXIS

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
	if inputs is None:
		print("ERROR: 'inputs' library not installed.")
		print("Run: pip install inputs")
		sys.exit(1)

	pygame.init()

	screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
	pygame.display.set_caption("Controller Right Stick Tracker")
	screen.set_alpha(255)
	clock = pygame.time.Clock()

	font_title = pygame.font.SysFont("consolas", 28, bold=True)
	font_body = pygame.font.SysFont("consolas", 22)
	font_small = pygame.font.SysFont("consolas", 18)

	print("Initializing input listener (works in background even when unfocused)...")
	output_path = get_unique_output_path(OUTPUT_DIR, OUTPUT_FILE)
	print(f"Saving outputs to {output_path}")
	
	poller = JoystickPoller(output_path)
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
