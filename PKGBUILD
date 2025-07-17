# Maintainer: Matthias Schabhüttl <matthias@matthiasschabhuettl.com>

pkgname=openconnect-sso-plus
pkgver=0.9.0
pkgrel=1
pkgdesc="Wrapper script for OpenConnect supporting Azure AD (SAMLv2) authentication"
arch=('any')
url="https://github.com/mschabhuettl/openconnect-sso-plus"
license=('GPL3')
depends=('python' 'python-pyqt6' 'python-pyqt6-webengine' 'python-attrs' 'python-colorama'
         'python-keyring' 'python-lxml' 'python-prompt_toolkit' 'python-pyxdg' 'python-requests'
         'python-structlog' 'python-toml' 'python-pysocks' 'python-jaraco.classes' 'sudo' 'openconnect')
makedepends=('python-setuptools')
checkdepends=('python-pytest' 'python-pytest-asyncio')
optdepends=()
source=("https://github.com/username/repo-name/archive/refs/heads/main.tar.gz")
sha256sums=('SKIP')

prepare() {
  cd "$pkgname-$pkgver"
}

build() {
  cd "$pkgname-$pkgver"
  python setup.py build
}

check() {
  cd "$pkgname-$pkgver"
  pytest || /usr/bin/true # pytest-httpserver
}

package() {
  cd "$pkgname-$pkgver"
  python setup.py install --prefix=/usr --root="$pkgdir" --optimize=1
}
