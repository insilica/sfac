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
    srvc.url = "github:insilica/rs-srvc";
  };
  outputs = { self, nixpkgs, flake-utils, poetry2nix, srvc, ... }@inputs:
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
        ctdbase-relations-package = mkPoetryApplication {
          inherit overrides;
          preferWheels = true;
          projectDir = ./ctdbase-relations;
        };
        ctdbase-relations = stdenv.mkDerivation {
          name = "sfac-ctdbase-relations";
          src = ./ctdbase-relations;
          buildInputs = [ ctdbase-relations-package.dependencyEnv ];
          installPhase = ''
            mkdir -p $out
            cp -r bin $out
          '';
        };
        finetune-answers-package = mkPoetryApplication {
          inherit overrides;
          preferWheels = true;
          projectDir = ./finetune-answers;
        };
        finetune-answers = stdenv.mkDerivation {
          name = "sfac-finetune-answers";
          src = ./finetune-answers;
          buildInputs = [ finetune-answers-package.dependencyEnv ];
          installPhase = ''
            mkdir -p $out
            cp -r bin $out
          '';
        };
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
        openai-label-package = mkPoetryApplication {
          inherit overrides;
          preferWheels = true;
          projectDir = ./openai-label;
        };
        openai-label = stdenv.mkDerivation {
          name = "sfac-openai-label";
          src = ./openai-label;
          buildInputs = [ openai-label-package.dependencyEnv ];
          installPhase = ''
            mkdir -p $out
            cp -r bin $out
          '';
        };
      in {
        packages = {
          inherit ctdbase-relations finetune-answers gpt-label gpt4-label
            openai-label;
        };
        devShells.default = mkShell {
          buildInputs =
            [ openai-full poetry2nix.packages.${system}.poetry srvc.packages.${system}.default ];
        };
      });
}
