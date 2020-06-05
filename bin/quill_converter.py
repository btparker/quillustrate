from plumbum import cli
from quillustrate.engines.quill import QuillConverterEngine

class QuillAsciiConverter(cli.Application):
    input = cli.SwitchAttr(
        ['--input'],
        argtype=str,
        mandatory=True,
        help='Path to (desired) input dir',
    )

    output = cli.SwitchAttr(
        ['--output'],
        argtype=str,
        mandatory=True,
        help='Path to (desired) output dir',
    )

    def main(self):
        QuillConverterEngine.bin_to_ascii(
            input_proj_dir=self.input,
            output_proj_dir=self.output,
        )

if __name__ == '__main__':
    QuillAsciiConverter.run()
