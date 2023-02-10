{
  description = "sfac";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    flake-compat = {
      url = "github:edolstra/flake-compat";
      flake = false;
    };
    srvc = {
      url = "github:insilica/rs-srvc/v0.14.0";
      inputs.flake-compat.follows = "flake-compat";
      inputs.flake-utils.follows = "flake-utils";
      inputs.nixpkgs.follows = "nixpkgs";
    };
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
