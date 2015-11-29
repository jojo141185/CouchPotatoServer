# -*- coding: utf-8 -*-

from couchpotato.core.logger import CPLog
from couchpotato.core.media._base.providers.och.bestmovies import Base
from couchpotato.core.media.movie.providers.base import MovieProvider

log = CPLog(__name__)

autoload = 'bestmovies'

class bestmovies(MovieProvider, Base):
    pass