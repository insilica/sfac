# SFAC - Susceptibility Factors SRVC

## Get Started
(1) [Install nix](https://nixos.org/download.html) (2) clone sfac (3) start nix-shell (slow the first time).  

```sh
gh repo clone insilica/sfac && cd sfac
nix-shell  
```

In the nix shell you can now use the SRVC tool `sr` to run flows:
```sh
sr flow feedback   # start a review user interface
Listening on http://127.0.0.1:6003
```
