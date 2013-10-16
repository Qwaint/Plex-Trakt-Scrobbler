from core.helpers import add_attribute
from core.http import responses

# Regular Expressions for GUID parsing
MOVIE_REGEXP = Regex('com.plexapp.agents.*://(?P<imdb_id>tt[-a-z0-9\.]+)')
MOVIEDB_REGEXP = Regex('com.plexapp.agents.themoviedb://(?P<tmdb_id>[0-9]+)')
STANDALONE_REGEXP = Regex('com.plexapp.agents.standalone://(?P<tmdb_id>[0-9]+)')

TVSHOW_REGEXP = Regex('com.plexapp.agents.(thetvdb|abstvdb|xbmcnfotv)://(?P<tvdb_id>[-a-z0-9\.]+)/'
                      '(?P<season>[-a-z0-9\.]+)/(?P<episode>[-a-z0-9\.]+)')
TVSHOW1_REGEXP = Regex('com.plexapp.agents.(thetvdb|abstvdb|xbmcnfotv)://([-a-z0-9\.]+)')

MOVIE_PATTERNS = [
    MOVIE_REGEXP,
    MOVIEDB_REGEXP,
    STANDALONE_REGEXP
]

PMS_URL = 'http://localhost:32400%s'


class PMS:
    def __init__(self):
        pass

    @classmethod
    def add_guid(cls, metadata, section):
        guid = section.get('guid')
        if not guid:
            return

        if section.get('type') == 'movie':

            # Cycle through patterns and try get a result
            for pattern in MOVIE_PATTERNS:
                match = pattern.search(guid)

                # If we have a match, update the metadata
                if match:
                    metadata.update(match.groupdict())
                    return

            Log('The movie %s doesn\'t have any imdb or tmdb id, it will be ignored.' % section.get('title'))
        elif section.get('type') == 'episode':
            match = TVSHOW_REGEXP.search(guid)

            # If we have a match, update the metadata
            if match:
                metadata.update(match.groupdict())
            else:
                Log('The episode %s doesn\'t have any tmdb id, it will not be scrobbled.' % section.get('title'))
        else:
            Log('The content type %s is not supported, the item %s will not be scrobbled.' % (
                section.get('type'), section.get('title')
            ))

    @classmethod
    def get_server_info(cls):
        return XML.ElementFromURL(PMS_URL % '', errors='ignore')

    @classmethod
    def get_server_version(cls, default=None):
        server_info = cls.get_server_info()
        if not server_info:
            return default

        return server_info.attrib.get('version') or default

    @classmethod
    def get_status(cls):
        return XML.ElementFromURL(PMS_URL % '/status/sessions', errors='ignore')

    @classmethod
    def get_video_session(cls, session_key):
        try:
            xml_content = cls.get_status().xpath('//MediaContainer/Video')

            for section in xml_content:
                if section.get('sessionKey') == session_key and '/library/metadata' in section.get('key'):
                    return section

        except Ex.HTTPError:
            Log.Error('Failed to connect to PMS.')
        except Ex.URLError:
            Log.Error('Failed to connect to PMS.')

        Log.Warn('Session not found')
        return None

    @classmethod
    def get_metadata(cls, key):
        return XML.ElementFromURL(PMS_URL % ('/library/metadata/%s' % key), errors='ignore')

    @classmethod
    def get_metadata_guid(cls, key):
        return cls.get_metadata(key).xpath('//Directory')[0].get('guid')

    @classmethod
    def get_metadata_leaves(cls, key):
        return XML.ElementFromURL(PMS_URL % ('/library/metadata/%s/allLeaves' % key), errors='ignore')

    @classmethod
    def get_sections(cls):
        return XML.ElementFromURL(PMS_URL % '/library/sections', errors='ignore').xpath('//Directory')

    @classmethod
    def get_section(cls, name):
        return XML.ElementFromURL(PMS_URL % ('/library/sections/%s/all' % name), errors='ignore')

    @classmethod
    def get_section_directories(cls, section):
        return cls.get_section(section).xpath('//Directory')

    @classmethod
    def get_section_videos(cls, section):
        return cls.get_section(section).xpath('//Video')

    @classmethod
    @route('/applications/trakttv/get_metadata_from_pms')
    def metadata(cls, item_id):
        # Prepare a dict that contains all the metadata required for trakt.
        try:
            xml_content = PMS.get_metadata(str(item_id)).xpath('//Video')

            for section in xml_content:
                metadata = {}

                # Add attributes if they exist
                add_attribute(metadata, section, 'duration', float, lambda x: int(x / 60000))
                add_attribute(metadata, section, 'year', int)

                add_attribute(metadata, section, 'lastViewedAt', int, target_key='last_played')
                add_attribute(metadata, section, 'viewCount', int, target_key='plays')

                add_attribute(metadata, section, 'type')

                if metadata['type'] == 'movie':
                    metadata['title'] = section.get('title')

                elif metadata['type'] == 'episode':
                    metadata['title'] = section.get('grandparentTitle')
                    metadata['episode_title'] = section.get('title')

                # Add guid match data
                cls.add_guid(metadata, section)

                return metadata

        except Ex.HTTPError, e:
            Log('Failed to connect to %s.' % PMS_URL)
            return {'status': False, 'message': responses[e.code][1]}
        except Ex.URLError, e:
            Log('Failed to connect to %s.' % PMS_URL)
            return {'status': False, 'message': e.reason[0]}

    @classmethod
    def scrobble(cls, video):
        if video.get('viewCount') > 0:
            Log('video has already been marked as seen')
            return False

        HTTP.Request('http://localhost:32400/:/scrobble?identifier=com.plexapp.plugins.library&key=%s' % (
            video.get('ratingKey')
        ), immediate=True)

        return True

    @classmethod
    def rate(cls, video, rating):
        HTTP.Request('http://localhost:32400/:/rate?key=%s&identifier=com.plexapp.plugins.library&rating=%s' % (
            video.get('ratingKey'), rating
        ), immediate=True)

        return True