import xml.etree.ElementTree as ET
from io import BytesIO
from CaesarAITorrentParsers.models.TorrentItem import TorrentItem
from CaesarAIConstants import CaesarAIConstants
from typing import List, AsyncGenerator
import requests
import json
from CaesarAIRedis import CaesarAIRedis
class CaesarAIJackett:
    def __init__(self,url) -> None:
        # Extract relevant data
        self.response = requests.get(url)
        xml = self.response.content
        self.namespace = {'atom': 'http://www.w3.org/2005/Atom', 'torznab': 'http://torznab.com/schemas/2015/feed'}
        tree = ET.parse(BytesIO(xml))
        self.root = tree.getroot()
        self.torrent_items:List[TorrentItem]= []
    @staticmethod
    def get_all_torrent_indexers():
        cr = CaesarAIRedis()
        if not cr.getkey("indexers"):
            url = f"{CaesarAIConstants.BASE_JACKETT_URL}{CaesarAIConstants.ALL_INDEXERS_SUFFIX}?apikey={CaesarAIConstants.JACKETT_API_KEY}"
            response = requests.get(url)
            indexers_data = response.json()["Indexers"]
            indexers = list(set([indexer["ID"] for indexer in indexers_data]))
            cr.setkey("indexers",json.dumps(indexers))
            return indexers
        else:
            indexers = cr.getkey("indexers")
            return json.loads(indexers)
    @staticmethod
    async def single_episode_streamer(title:str,season:int,episode:int,indexers:List[str]):
        for indexer in indexers:
            print(indexer)
            url = f"{CaesarAIConstants.BASE_JACKETT_URL}{CaesarAIConstants.TORZNAB_ALL_SUFFIX.replace('all',indexer)}?apikey={CaesarAIConstants.JACKETT_API_KEY}&t={CaesarAIConstants.ENDPOINT}&q={title}&season={season}&ep={episode}"
            caejackett = CaesarAIJackett(url)
            torrentinfo = caejackett.get_torrent_info()
            torrentinfo = caejackett.get_single_episodes()
            yield '{"episodes": ['  # Start of JSON array
            first = True
            for torrent in torrentinfo:
                if not first:
                    yield ','  # Comma between JSON objects
                first = False
                yield json.dumps(torrent.dict())
            yield ']}'  # End of JSON array


    def get_torrent_info(self,verbose=0) -> List[TorrentItem]:
    
        
        for item in self.root.findall(".//item"):
            title = item.find("title").text if item.find("title") is not None else "N/A"
            guid = item.find("guid").text if item.find("guid") is not None else "N/A"
            pub_date = item.find("pubDate").text if item.find("pubDate") is not None else "N/A"
            size = item.find("size").text if item.find("size") is not None else "N/A"
            magnet_link = item.find("link").text if item.find("link") is not None else "N/A"
            indexer = item.find("jackettindexer").text if item.find("jackettindexer") is not None else "N/A"
            # Extract torznab attributes
            categories = [attr.get("value") for attr in item.findall("torznab:attr[@name='category']", self.namespace)]
            seeders = item.find("torznab:attr[@name='seeders']", self.namespace)
            peers = item.find("torznab:attr[@name='peers']", self.namespace)

            seeders = seeders.get("value") if seeders is not None else "N/A"
            peers = peers.get("value") if peers is not None else "N/A"
            if verbose == 1:
                # Print extracted data
                print(f"Title: {title}")
                print(f"Indexer: {indexer}")
                print(f"GUID: {guid}")
                print(f"Published Date: {pub_date}")
                print(f"Size: {size}")
                print(f"Magnet Link: {magnet_link}")
                print(f"Categories: {categories}")
                print(f"Seeders: {seeders}")
                print(f"Peers: {peers}")
                print("-" * 50)

            # Create Pydantic model instance
            torrent = TorrentItem(
                title=title,
                guid=guid,
                pub_date=pub_date,
                size=size,
                magnet_link=magnet_link,
                categories=categories,
                seeders=seeders,
                peers=peers,
                indexer=indexer
            )
            self.torrent_items.append(torrent)
        return self.torrent_items
    def get_largest_file(self) -> List[TorrentItem]:
        return sorted(self.torrent_items, key=lambda x: x.size or 0, reverse=True)
    def get_largest_file_with_highest_seeders(self) -> List[TorrentItem]:
        return sorted(self.torrent_items, key=lambda x: ( x.size and x.seeders)or 0 , reverse=True)
    def get_single_episodes(self) -> List[TorrentItem]:
        return list(filter(lambda x:self.is_single(x) and self.not_torrent_only_magnet(x),self.torrent_items))
    def get_batch_episodes(self)-> List[TorrentItem]:
        return list(filter(lambda x:self.is_batch and self.not_torrent_only_magnet(x),self.torrent_items))
    def get_single_and_multi_audio(self)-> List[TorrentItem]:
        return list(filter(lambda x:x.is_multi_audio and self.not_torrent_only_magnet(x),self.get_single_episodes()))
    def not_torrent_only_magnet(self,x:TorrentItem):
        return "magnet:?xt=" in x.magnet_link
    def is_batch(self,x:TorrentItem):
        return type(x.episode) == list
    def is_single(self,x:TorrentItem):
        return type(x.episode) != list
