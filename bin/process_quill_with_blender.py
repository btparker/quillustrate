from plumbum import cli


class ProcessQuillWithBlender(cli.Application):
    alembic_input = cli.SwitchAttr(
        ['--alembic-input'],
        default=None,
        argtype=str,
        excludes=['quill-input'],
        help='Alembic input (.abc), exported from Quill',
    )

    quill_input = cli.SwitchAttr(
        ['--quill-input'],
        default=None,
        argtype=str,
        excludes=['alembic-input'],
        help='Quill input (project directory)',
    )

    output = cli.SwitchAttr(
        ['--output'],
        argtype=str,
        mandatory=True,
        help='Path to (desired) output dir',
    )

    def main(self):
        import os
        from quillustrate.engines import BlenderEngine, QuillExporterEngine

        if not os.path.exists(self.output):
            os.makedirs(self.output)

        blender_engine = BlenderEngine()

        if self.quill_input:
            quill_exporter_engine = QuillExporterEngine()
        else:
            blender_engine.process_quill_alembic(
                alembic_path=self.alembic_input,
                output=self.output,
            )

if __name__ == '__main__':
    ProcessQuillWithBlender.run()