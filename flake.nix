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
  };
  outputs = { self, nixpkgs, flake-utils, poetry2nix, ... }@inputs:
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
        gpt4-label-package = mkPoetryApplication {
          inherit overrides;
          preferWheels = true;
          projectDir = ./gpt4-label;
        };
        gpt4-label = stdenv.mkDerivation {
          name = "sfac-gpt4-label";
          src = ./gpt4-label;
          buildInputs = [ gpt4-label-package.dependencyEnv ];
          installPhase = ''
            mkdir -p $out
            cp -r bin $out
          '';
        };
      in {
        packages = { inherit gpt-label gpt4-label; };
        devShells.default = mkShell {
          buildInputs = [ poetry2nix.packages.${system}.poetry srvc ];
        };
      });
}
