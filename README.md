# openconnect-sso-plus

Wrapper script for OpenConnect supporting Azure AD (SAMLv2) authentication
to Cisco SSL-VPNs

[![Tests Status](https://github.com/mschabhuettl/openconnect-sso-plus/workflows/Tests/badge.svg?branch=main&event=push)](https://github.com/mschabhuettl/openconnect-sso-plus/actions?query=workflow%3ATests+branch%3Amain+event%3Apush)

This repository is a fork of [vlaci/openconnect-sso](https://github.com/vlaci/openconnect-sso) with additional improvements.

## Installation

### Using pip/pipx

A generic way that works on most 'standard' Linux distributions out of the box.
The following example shows how to install `openconnect-sso-plus` along with its
dependencies including Qt:

```shell
$ pip install --user pipx
Successfully installed pipx
$ pipx install "openconnect-sso[full]"
⣾ installing openconnect-sso
  installed package openconnect-sso 0.4.0, Python 3.7.5
  These apps are now globally available
    - openconnect-sso
⚠️  Note: '/home/vlaci/.local/bin' is not on your PATH environment variable.
These apps will not be globally accessible until your PATH is updated. Run
`pipx ensurepath` to automatically add it, or manually modify your PATH in your
shell's config file (i.e. ~/.bashrc).
done! ✨ 🌟 ✨
Successfully installed openconnect-sso
$ pipx ensurepath
Success! Added /home/vlaci/.local/bin to the PATH environment variable.
Consider adding shell completions for pipx. Run 'pipx completions' for
instructions.

You likely need to open a new terminal or re-login for the changes to take
effect. ✨ 🌟 ✨
```

Of course you can also install via `pip` instead of `pipx` if you'd like to
install system-wide or a virtualenv of your choice.

### On Arch Linux

There is an unofficial package available for Arch Linux on
[AUR](https://aur.archlinux.org/packages/openconnect-sso/). You can use your
favorite AUR helper to install it:

``` shell
yay -S openconnect-sso
```

### Using nix

The easiest method to try is by installing directly:

```shell
$ nix-env -i -f https://github.com/mschabhuettl/openconnect-sso-plus/archive/main.tar.gz
unpacking 'https://github.com/mschabhuettl/openconnect-sso-plus/archive/main.tar.gz'...
[...]
installing 'openconnect-sso-0.4.0'
these derivations will be built:
  /nix/store/2z47740z1rr2cfqfin5lnq04sq3c5xjg-openconnect-sso-0.4.0.drv
[...]
building '/nix/store/50q496iqf840wi8b95cfmgn07k6y5b59-user-environment.drv'...
created 606 symlinks in user environment
$ openconnect-sso
```

An overlay is also available to use in nix expressions:

``` nix
let
  openconnectOverlay = import "${builtins.fetchTarball https://github.com/mschabhuettl/openconnect-sso-plus/archive/main.tar.gz}/overlay.nix";
  pkgs = import <nixpkgs> { overlays = [ openconnectOverlay ]; };
in
  #  pkgs.openconnect-sso is available in this context
```

... or to use in `configuration.nix`:

``` nix
{ config, ... }:

{
  nixpkgs.overlays = [
    (import "${builtins.fetchTarball https://github.com/mschabhuettl/openconnect-sso-plus/archive/main.tar.gz}/overlay.nix")
  ];
}
```

### Windows *(EXPERIMENTAL)*

Install with [pip/pipx](#using-pippipx) and be sure that you have `sudo` and `openconnect`
executable commands in your PATH.

## Usage

If you want to save credentials and get them automatically
injected in the web browser:

```shell
$ openconnect-sso --server vpn.server.com/group --user user@domain.com
Password (user@domain.com):
[info     ] Authenticating to VPN endpoint ...
```

User credentials are automatically saved to the users login keyring (if
available).

If you already have Cisco AnyConnect set-up, then `--server` argument is
optional. Also, the last used `--server` address is saved between sessions so
