import difflib
from plumbum import cli

class FileDiff(cli.Application):
    file_a = cli.SwitchAttr(
        ['-a'],
        default=None,
        argtype=str,
        help='File A',
    )

    file_b = cli.SwitchAttr(
        ['-b'],
        default=None,
        argtype=str,
        help='File B',
    )

    def main(self):
        with open(self.file_a) as fa:
            fa_text = fa.read()
        with open(self.file_b) as fb:
            fb_text = fb.read()
        # Find and print the diff:
        for line in difflib.unified_diff(fa_text, fb_text):
            print(line)

if __name__ == '__main__':
    FileDiff.run()
