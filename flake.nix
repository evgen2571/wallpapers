{
  description = "My wallpaper collection";

  outputs = { self }: {
    homeManagerModules.default =
      { config, lib, ... }:
      let
        cfg = config.wallpapers;
      in
      {
        options.wallpapers = {
          enable = lib.mkEnableOption "my wallpaper collection";
          directory = lib.mkOption {
            type = lib.types.str;
            default = "${config.home.homeDirectory}/Pictures/Wallpapers";
            description = "Directory in the home directory where wallpapers are linked.";
          };
        };

        config = lib.mkIf cfg.enable {
          home.file.wallpapers = {
            source = ./wallpapers;
            target = cfg.directory;
            recursive = true;
          };
        };
      };
  };
}
