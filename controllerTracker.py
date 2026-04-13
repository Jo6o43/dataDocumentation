import sys
import pygame


WINDOW_WIDTH = 700
WINDOW_HEIGHT = 420
FPS = 60
DEADZONE = 0.08


def clamp(value, min_value, max_value):
	return max(min_value, min(max_value, value))


def apply_deadzone(value, deadzone):
	if abs(value) < deadzone:
		return 0.0
	return value


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


def main():
	pygame.init()
	pygame.joystick.init()

	screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
	pygame.display.set_caption("Controller Right Stick Tracker")
	clock = pygame.time.Clock()

	font_title = pygame.font.SysFont("consolas", 28, bold=True)
	font_body = pygame.font.SysFont("consolas", 22)
	font_small = pygame.font.SysFont("consolas", 18)

	if pygame.joystick.get_count() == 0:
		print("No controller detected. Connect one and restart.")
		running = True
		while running:
			for event in pygame.event.get():
				if event.type == pygame.QUIT:
					running = False
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
					running = False

			screen.fill((20, 20, 24))
			draw_centered_text(screen, "No Controller Detected", font_title, (230, 230, 230), 170)
			draw_centered_text(screen, "Connect a gamepad and restart", font_body, (190, 190, 190), 220)
			draw_centered_text(screen, "Press ESC to quit", font_small, (160, 160, 160), 270)
			pygame.display.flip()
			clock.tick(FPS)

		pygame.quit()
		sys.exit(0)

	joystick = pygame.joystick.Joystick(0)
	joystick.init()
	joystick_name = joystick.get_name()

	axis_pair = pick_right_stick_axes(joystick)
	if axis_pair is None:
		print("Controller has no readable axes.")
		pygame.quit()
		sys.exit(1)

	axis_x, axis_y = axis_pair
	print(f"Controller: {joystick_name}")
	print(f"Tracking right stick axes: X={axis_x}, Y={axis_y}")

	previous_print = None
	running = True
	while running:
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				running = False
			elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
				running = False

		raw_x = joystick.get_axis(axis_x)
		raw_y = joystick.get_axis(axis_y)
		x = apply_deadzone(raw_x, DEADZONE)
		y = apply_deadzone(raw_y, DEADZONE)

		rounded_pair = (round(x, 3), round(y, 3))
		if rounded_pair != previous_print:
			print(f"Right Stick -> X: {rounded_pair[0]: .3f} | Y: {rounded_pair[1]: .3f}")
			previous_print = rounded_pair

		screen.fill((16, 18, 24))

		draw_centered_text(screen, "Right Stick Input", font_title, (235, 235, 235), 40)
		draw_centered_text(screen, f"Controller: {joystick_name}", font_small, (185, 200, 220), 78)
		draw_centered_text(screen, f"Axes: X={axis_x}  Y={axis_y}", font_small, (160, 180, 200), 102)
		draw_centered_text(screen, f"X: {x: .3f}", font_body, (230, 200, 120), 145)
		draw_centered_text(screen, f"Y: {y: .3f}", font_body, (150, 210, 255), 178)
		draw_centered_text(screen, "Press ESC to quit", font_small, (150, 150, 150), 395)

		box_size = 220
		box_x = WINDOW_WIDTH // 2 - box_size // 2
		box_y = 200
		pygame.draw.rect(screen, (90, 100, 120), (box_x, box_y, box_size, box_size), width=2)

		center_x = box_x + box_size // 2
		center_y = box_y + box_size // 2
		pygame.draw.line(screen, (60, 70, 85), (center_x, box_y), (center_x, box_y + box_size), width=1)
		pygame.draw.line(screen, (60, 70, 85), (box_x, center_y), (box_x + box_size, center_y), width=1)

		dot_x = int(center_x + clamp(x, -1.0, 1.0) * (box_size // 2 - 8))
		dot_y = int(center_y + clamp(y, -1.0, 1.0) * (box_size // 2 - 8))
		pygame.draw.circle(screen, (255, 180, 100), (dot_x, dot_y), 8)

		pygame.display.flip()
		clock.tick(FPS)

	pygame.quit()
	sys.exit(0)


if __name__ == "__main__":
	main()
