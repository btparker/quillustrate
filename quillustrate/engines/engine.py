class Engine(object):
    def run_cmd(self, args):
        from plumbum import local, FG

        cmd = local[self.command_string]
        cmd_with_args = cmd.bound_command(args)
        cmd_with_args & FG
