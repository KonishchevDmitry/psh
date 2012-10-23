# Maintainer: Nekolyanich <gmail@nekolyanich.com>
pkgname=python2-psh
pkgver=0.2.1
pkgrel=1
pkgdesc="psh allows you to spawn processes in Unix shell-style way"
arch=("i686" "x86_64")
url="http://konishchevdmitry.github.com/psh/"
license=("GPL3")
depends=("python2")
makedepends=("git")
provides=("python2-psh")
conflicts=()
replaces=()
backup=()
options=(!emptydirs)
source=()
md5sums=()

_gitroot="git://github.com/KonishchevDmitry/psh.git"
_gitname="psh"

build () {
  cd "$srcdir"
  msg "Connecting to GIT server...."

  if [ -d $_gitname ] ; then
    cd $_gitname && git pull origin
    msg "The local files are updated."
  else
    git clone $_gitroot $_gitname
  fi

  msg "GIT checkout done or server timeout"
  msg "Starting make..."

  rm -rf "$srcdir/$_gitname-build"
  git clone "$srcdir/$_gitname" "$srcdir/$_gitname-build"
  cd "$srcdir/$_gitname-build"
  python2 setup.py install --root="$pkgdir/" --optimize=1
}


# vim:set ts=2 sw=2 et:
