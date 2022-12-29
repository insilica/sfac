{
  description = "sfac";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-22.05";
    flake-utils.url = "github:numtide/flake-utils";
    srvc.url = "github:insilica/rs-srvc";
  };
  outputs = { self, nixpkgs, flake-utils, srvc, ... }@inputs:
    flake-utils.lib.eachDefaultSystem (system:
      with import nixpkgs { inherit system; };
      let
        sfac = stdenv.mkDerivation {
          name = "sfac";
          src = ./.;

          installPhase = ''
            mkdir -p $out
          '';
        };
      in {
        packages = {
          inherit sfac;
          default = sfac;
        };
        devShells.default =
          mkShell { buildInputs = [ srvc.packages.${system}.default ]; };
      });
}
