# SFAC - Susceptibility Factors SRVC

## Get Started
First [install nix](https://nixos.org/download.html) then:

```sh
$ gh repo clone insilica/sfac && cd sfac
$ nix-shell
[nix-shell:/sfac]$ sr flow import
[nix-shell:/sfac]$ sr flow brat
http://127.0.0.1:42445
```

1. gh repo clone uses github cli to clone this project.
2. nix-shell starts a shell with all the required dependencies for this project.
3. sr flow import pulls documents for this project
4. sr flow brat starts a user interface for reviewing documents
5. the resulting server url allows you to open the UI in your browser

