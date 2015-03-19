# -*- coding: utf-8 -*-

from couchpotato.core.logger import CPLog
from couchpotato.core.media._base.providers.och.rslinks import Base
from couchpotato.core.media.movie.providers.base import MovieProvider

log = CPLog(__name__)

autoload = 'rslinks'

class rslinks(MovieProvider, Base):
    pass