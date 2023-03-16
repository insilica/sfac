{
  description = "sfac";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    flake-compat = {
      url = "github:edolstra/flake-compat";
      flake = false;
    };
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.flake-utils.follows = "flake-utils";
      inputs.nixpkgs.follows = "nixpkgs";
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
  outputs =
    { self, nixpkgs, flake-utils, poetry2nix, srvc, srvc-server, ... }@inputs:
    flake-utils.lib.eachDefaultSystem (system:
      with import nixpkgs { inherit system; };
      let
        inherit (poetry2nix.legacyPackages.${system})
          defaultPoetryOverrides mkPoetryApplication mkPoetryEnv;
        overrides = defaultPoetryOverrides.extend (self: super: {
          llama-index = super.llama-index.overridePythonAttrs (old: {
            propagatedBuildInputs = (old.propagatedBuildInputs or [ ])
              ++ [ super.setuptools ];
          });
        });
        gpt-label-package = mkPoetryApplication {
          inherit overrides;
          preferWheels = true;
          projectDir = ./gpt-label;
        };
        gpt-label = stdenv.mkDerivation {
          name = "sfac-gpt-label";
          src = ./gpt-label;
          buildInputs = [ gpt-label-package.dependencyEnv ];
          installPhase = ''
            mkdir -p $out
            cp -r bin $out
          '';
        };
      in {
        packages = { inherit gpt-label; };
        devShells.default = mkShell {
          buildInputs = [
            srvc.packages.${system}.default
            srvc-server.packages.${system}.default
          ];
        };
      });
}
