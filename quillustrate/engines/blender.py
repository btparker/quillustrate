import os
from quillustrate.engines import Engine

class BlenderEngine(Engine):
    command_string = "blender.exe"

    def process_quill_alembic(self, alembic_path, output):
        self.run({
            'alembic': alembic_path,
            'output': output,
        })


    def run(self, options={}, output):
        python_entry = os.path.join(
            os.path.dirname(__file__),
            'blender.py',
        )

        args = [
            '--background',
            '--python', python_entry,
            '--',
            '--output', output,
        ]

        for key, value in options.items():
            args.append('--{}'.format(key))
            args.append(value)

        self.run_cmd(args)
