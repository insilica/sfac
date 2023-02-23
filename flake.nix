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
      url = "github:insilica/rs-srvc/master";
      inputs.flake-compat.follows = "flake-compat";
      inputs.flake-utils.follows = "flake-utils";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    srvc-server = {
      url = "github:insilica/srvc-server";
      inputs.flake-compat.follows = "flake-compat";
      inputs.flake-utils.follows = "flake-utils";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.srvc.follows = "srvc";
    };
  };
  outputs = { self, nixpkgs, flake-utils, srvc, srvc-server, ... }@inputs:
    flake-utils.lib.eachDefaultSystem (system:
      with import nixpkgs { inherit system; }; {
        devShells.default = mkShell {
          buildInputs = [
            srvc.packages.${system}.default
            srvc-server.packages.${system}.default
          ];
        };
      });
}
