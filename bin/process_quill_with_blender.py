from plumbum import cli


class ProcessQuillWithBlender(cli.Application):
    alembic_input = cli.SwitchAttr(
        ['--alembic-input'],
        argtype=str,
        mandatory=True,
        help='Alembic input (.abc), exported from Quill',
    )

    output = cli.SwitchAttr(
        ['--output'],
        argtype=str,
        mandatory=True,
        help='Path to (desired) output dir',
    )

    def main(self):
        import os
        from quillustrate.engines import BlenderEngine
        
        if not os.path.exists(self.output):
            os.makedirs(self.output)

        blender_engine = BlenderEngine()
        blender_engine.process_quill_alembic(
            alembic_path=self.alembic_input,
            output=self.output,
        )

if __name__ == '__main__':
    ProcessQuillWithBlender.run()