import os

class Engine(object):
	def run_cmd(self, args):
		from plumbum import local, FG

		cmd = local[self.command_string]
		cmd_with_args = cmd.bound_command(args)
		cmd_with_args & FG


class BlenderEngine(Engine):
	command_string = "blender.exe"

	def process_quill_alembic(self, alembic_path, output):
		self.run({
			'alembic': alembic_path,
			'output': output,
		})


	def run(self, options={}):
		python_entry = os.path.join(
			os.path.dirname(__file__),
			'blender.py',
		)

		args = [
			'--background',
			'--python', python_entry,
			'--',
		]

		for key, value in options.items():
			args.append('--{}'.format(key))
			args.append(value)

		self.run_cmd(args)