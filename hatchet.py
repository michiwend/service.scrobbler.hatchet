import requests, time
from requests.exceptions import *
from datetime import datetime

class Token:

    def __init__( self, token, ttl ):
        self.update( token, ttl )


    def update( self, token, ttl ):
        self._token = token
        if ttl == 0:
            self._expire_time = 0
        else:
            # expire 10 seconds earlier to make sure a request is not made with
            # expired token
            self._expire_time = ttl + (time.time() - 10)


    def get_token( self ):
        return self._token


    def is_valid( self ):
        if self._expire_time > time.time() or self._expire_time == 0:
            return True

        return False



class HatchetService:

    AuthURL = 'https://auth.hatchet.is/v1/'
    BaseURL = 'https://api.hatchet.is/v2/'

    def __init__( self, user_agent, username, password ):
        # TODO: pass in tokens??
        self._bearer_token  = Token('', -1)
        self._refresh_token = Token('', -1)
        self._access_token  = Token('', -1)

        self._user_agent = user_agent
        self._username   = username
        self._password   = password

        self._playbacklog_entry_queue = []


    def _login( self ):
        print('LOGIN: ' + self._username + ':' + self._password)
        r = requests.post(self.AuthURL + 'authentication/password', data={
            'grant_type': 'password',
            'username':   self._username,
            'password':   self._password
            })

        if r.status_code != requests.codes.ok:
            if r.status_code == 400:
                print("probably wrong user/password")
            else:
                r.raise_for_status()

            return

        j = r.json()

        self._bearer_token.update( j['access_token'], j['expires_in'] )
        self._refresh_token.update( j['refresh_token'], j['refresh_token_expires_in'] )


    def _refresh_bearer_token( self ):
        print('REFRESHING TOKEN')
        if not self._refresh_token.is_valid():
            self._login()
            return

        r = requests.post(self.AuthURL + 'tokens/refresh/bearer', data={
            'grant_type':    'refresh_token',
            'refresh_token':  self._refresh_token.get_token()
            })

        j = r.json()

        self._bearer_token.update( j['access_token'], j['expires_in'] )


    def _fetch_access_token( self ):
        print('FETCHING ACCESS TOKEN')
        if not self._bearer_token.is_valid():
            self._refresh_bearer_token()

        r = requests.get(self.AuthURL + 'tokens/fetch/calumet', 
                headers={'Authorization': 'Bearer ' + self._bearer_token.get_token()})

        j = r.json()

        self._access_token.update( j['access_token'], j['expires_in'] )


    def _authed_post( self, url, data ):
        print('AUTHED POST: ' + url + '\n' + data.__str__())
        if not self._access_token.is_valid():
            self._fetch_access_token()

        print('USING TOKEN: ' + self._access_token.get_token())

        return requests.post(url, headers={
            'Authorization': 'Bearer ' + self._access_token.get_token(),
            'User-Agent':    self._user_agent
            }, json=data)


    def _scrobble_or_queue( self, playbacklog_entry ):
        try:
            r = self._authed_post(self.BaseURL + 'playbacklogEntries', playbacklog_entry)
            r.raise_for_status()
        except (ConnectionError, Timeout, TooManyRedirects):
            # Request may have been correct but there was a network problem
            # --> queue the entry for later retry.
            if playbacklog_entry not in self._playbacklog_entry_queue:
                print("request failed, queing plentry")
                self._playbacklog_entry_queue.append(playbacklog_entry)


    def scrobble( self, artist, album, track, timestamp=None ):
        if not isinstance(timestamp, datetime):
            timestamp = datetime.utcnow()

        self._scrobble_or_queue(
                {'playbacklogEntry': {
                    'artistString': artist.strip().lower(),
                    'albumString':  album.strip().lower(),
                    'trackString':  track.strip().lower(),
                    'type':         'scrobble',
                    'duration':     -1, #FIXME
                    'timestamp':    timestamp.isoformat("T") + "Z"
                    }
                })


    def now_playing( self, artist, album, track ):
        body = {'playbacklogEntry': {
                    'artistString': artist.strip().lower(),
                    'albumString':  album.strip().lower(),
                    'trackString':  track.strip().lower(),
                    'type':         'nowplaying',
                    }
                }

        r = self._authed_post(self.BaseURL + 'playbacklogEntries', body)
        r.raise_for_status()
