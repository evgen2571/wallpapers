{ nixpkgs, homeManager }:
let
  pkgs = import nixpkgs { };
  evaluate =
    settings:
    (homeManager.lib.homeManagerConfiguration {
      inherit pkgs;
      modules = [
        ((import ../flake.nix).outputs { self = { }; }).homeManagerModules.default
        {
          home.username = "wallpaper-test";
          home.homeDirectory = "/home/wallpaper-test";
          home.stateVersion = "25.11";
          wallpapers = settings;
        }
      ];
    }).config;
  disabled = evaluate { };
  enabled = evaluate { enable = true; };
  custom = evaluate {
    enable = true;
    directory = "/home/wallpaper-test/Custom Wallpapers";
  };
in
assert !disabled.wallpapers.enable;
assert !(disabled.home.file ? wallpapers);
assert enabled.home.file.wallpapers.target == "Pictures/Wallpapers";
assert custom.home.file.wallpapers.target == "Custom Wallpapers";
assert enabled.home.file.wallpapers.recursive;
assert !enabled.home.file.wallpapers.force;
assert enabled.home.file.wallpapers.source == ../wallpapers;
true
