from processor import (
                        UrlFixer, 
                        UrlSearch, 
                        pagination_link,
                        Get_ID, 
                        pretty_size, 
                        validatename, 
                        HlsObject, 
                        pick_quality, 
                        list_quality
)
from Lib import Goscraper, Prettify, EpisodeScraper, ConsumetAPI, GogoCDN
import version
from Varstorage import Configuration, Constants
from pathlib import Path
import time, os
from terminology import in_green
import argparse
import sys
config = Configuration().load()
config.self_check()

#GlobalVar
chosen_quality_manual = None

def user_input(text, valid: list, msg="Enter valid variables"):
    "Get a list of valid integers, add any on list to allow any input other than blank or whitespace"
    user = None
    while True:
        user = input(text).strip()
        try:
            user = int(user)
        except ValueError:
            if "int" in valid:
                print(msg)
                continue
        if user and "any" in valid:
            return user
        if user in valid:
            return user
        if isinstance(user, int) and "int" in valid:
            return user
        print(msg)

def Episode_UI(url, anime_title, starting_ep=None, ending_ep=None):
       #"Collect episodes and UI for bulk download"
    goepisode = EpisodeScraper(url)
    available_episodes = goepisode.get_episodes()
    preprint = Prettify()
    preprint.define_alignment(tabs=1)
    preprint.add_tab()
    preprint.add_line(f"Found {available_episodes} episodes!")
    preprint.add_tab("Bulk downloader")
    preprint()
    if starting_ep == None:
        starting_ep = user_input(text="Start from episode:", valid=[i+1 for i in range(available_episodes)], msg="Enter valid number")
    if ending_ep == None:
        ending_ep = user_input(text="End at episode:", valid=[i+1 for i in range(available_episodes)], msg="Enter valid number")
    for i in range(starting_ep, ending_ep+1):
        preprint = Prettify()
        preprint.define_alignment(tabs=1)
        preprint.add_tab()
        preprint.add_line(f"Downloading Episode {i} / {ending_ep}")
        preprint.add_tab()
        preprint()
        episode_link = goepisode.get_episode_link(i)
        exit_code = Download_UI(episode_link, anime_title=anime_title, episode_number=i)
        if exit_code == 2:
            return exit_code

def Download_UI(url, anime_title, episode_number):
    "Get download links and show download UI"
    Path(Constants.download_folder).mkdir(parents=True, exist_ok=True) #Create Downloads folder
    #===
    preprint = Prettify()
    preprint.define_alignment(tabs=1)
    preprint.add_tab()
    preprint.add_line("Getting m3u8 file...")
    preprint.add_tab(char="-")
    preprint()
    video_id = Get_ID(url)
    if config.video_source == config.valid_video_source[1]:
        consumet = ConsumetAPI(base_url=config.get_consumet_api, video_id=video_id,source=config.get_consumet_video_server)
        video_data = consumet.get_m3u8_files()
        headers = consumet.get_referrer()
    elif config.video_source == config.valid_video_source[0]:
        gogocdn = GogoCDN(url)
        video_data = gogocdn.get_streaming_data()
        video_data = video_data.get_sources()
        headers = gogocdn.get_referrer()
    global chosen_quality_manual
    if config.video_quality_mode == "manual" and not chosen_quality_manual:
        qualities = list_quality(video_data)
        prettyqual = Prettify()
        prettyqual.define_alignment(tabs=1)
        prettyqual.add_line("Manual Mode enabled")
        prettyqual.add_tab(data="Available Quality",char="-")
        for quality in qualities:
            prettyqual.add_line(quality)
        prettyqual.add_tab(char="-")
        prettyqual()
        quality = user_input("Select Quality:", valid=qualities, msg="Incorrect input")
        chosen_quality_manual = quality
        video = pick_quality(video_data, preferred_quality=quality, force=True)
    elif chosen_quality_manual:
        video = pick_quality(video_data, preferred_quality=chosen_quality_manual, force=True)
    elif config.video_quality_mode == "auto":
        video = pick_quality(video_data, preferred_quality=config.video_quality_preference)
    print(f"Source: {config.video_source}")
    if config.video_quality_mode != "manual": print(f"Preferred Quality: {config.video_quality_preference}")
    print(f"Quality Selected: {video['quality']}")
    if not video:
        print("We are not able to find streamable media for this title")
        return 1
    #Download the file
    file_name = validatename(f"{anime_title}_{video['quality']}_{episode_number}")
    hls = HlsObject(m3u8_url=video['url'], headers=headers,file_name=file_name, download_location=os.path.join(Constants.download_folder, validatename(anime_title)))
    pickedurl = hls.get_m3u8_url()
    try: 
        print(pickedurl)
    except: 
        pass
    hls.download() #Initiate download
    print(f"Downloading: {anime_title}")
    error_msg = ""
    try:
        while True:
            hls.update_progress()
            segment_done = hls.progress['progress']
            segment_available = hls.segment_count
            segment_errored = hls.progress['errored']
            data_downloaded = hls.progress['file_size']
            try:
                percent_done = round(segment_done / segment_available * 100, 2)
            except ZeroDivisionError:
                percent_done = 0
            if segment_errored:
                error_msg = f"/Err:{segment_errored}"
            print(in_green(f"=== Progress: [{segment_done}/{segment_available}]{error_msg} ** {percent_done}% - {pretty_size(data_downloaded)} ==="), end="\r")
            if segment_done == segment_available:
                print("\n Download successful!")
                hls.arrange_files()
                hls.cache_clear()
                break
            time.sleep(1)
    except KeyboardInterrupt:
        hls.close()
        return 2

def Genre_UI():
    "Show available genres on site"
    gogo_page = Goscraper(config.get_host)
    genre_list = gogo_page.get_genres()
    preprint = Prettify()
    preprint.define_alignment(tabs=1)
    preprint.add_tab(data="Found Genres", lines=33)
    valid = []
    for num, genre_each in enumerate(genre_list):
        preprint.add_sort(key=num+1, value=genre_each['genre-name'], separator=".")
        valid.append(num+1)
    preprint.add_tab(char='-',lines=33)
    preprint()
    selection = user_input("Select:", valid=valid)
    new_url = UrlFixer(config.get_host, genre_list[selection-1]['flair'])
    print("\tLoading (restart if it took >10s)")
    return Home_UI(host=new_url)

def Home_UI(host, precannedselection = None):
    'Display main results'
    gogo_page = Goscraper(host)
    if not gogo_page.get_result_count():
        print("\tThere are no results found")
        return 1
    result_title = gogo_page.get_titles()
    pagination = gogo_page.get_pagination()
    preprint = Prettify()
    preprint.define_alignment(tabs=1)
    preprint.add_tab("Results",lines=33)
    valid = []
    for num, res_tile in enumerate(result_title):
        preprint.add_sort(key=num+1, value=res_tile["title_name"], separator=".)")
        if res_tile.get('episode'):
            preprint.add_line(f"\t Episode: {res_tile['episode']}")
        preprint.add_tab(char="-",lines=33)
        valid.append(num+1)
    [valid.append(each) for each in Constants.pagination_commands]
    preprint.add_line(f"There are {gogo_page.get_result_count()} results found")
    if pagination['page_total'] > 1:
        preprint.add_line("To switch a page: << or >>")
        preprint.add_line(f"Page: {pagination['page_on']}/{pagination['page_total']}")
    preprint()
    while True: #use loops to prevent halting of application for when pagination returns None

        if precannedselection is not None and (isinstance(precannedselection , int) or isinstance(int(precannedselection), int)) and precannedselection > 0 :
            selection = int(precannedselection)
        else :
            selection = user_input("Select:", valid=valid)

        if selection in Constants.pagination_commands:
            if selection == Constants.pagination_commands[0] or selection == Constants.pagination_commands[3]:
                #Forwards
                result = pagination_link(host, pagination['page_on'], pagination['page_total'], 'fwd')
            elif selection == Constants.pagination_commands[1] or selection == Constants.pagination_commands[2]:
                #Backwards
                result = pagination_link(host, pagination['page_on'], pagination['page_total'], 'prv')
            if result:
                return Home_UI(result)
        else:
            new_url = UrlFixer(config.get_host, result_title[selection-1]['flair']) #Use base url for this
            if res_tile.get('episode'):
                return Download_UI(new_url, result_title[selection-1]['title_name'], result_title[selection-1]['episode'])#This needs to go straight to Downloader or Video Scraper
            return Episode_UI(new_url, result_title[selection-1]['title_name'])
            #Next step is get download link and or skip to episode download

def ResultZone(mode, value=None, indexspecified=False, index = 0):
    if mode == "Home":
        return Home_UI(config.get_host)        
    elif mode == "Genre":
        Genre_UI()
    elif mode == "Search":
        if indexspecified == False:
            return Home_UI(UrlSearch(value))
        if indexspecified == True:
            return  Home_UI(UrlSearch(value), index)

def main():
    preprint = Prettify()
    preprint.define_alignment(tabs=1)
    preprint.add_tab(lines=33)
    preprint.define_alignment(tabs=1, spaces=5)
    preprint.add_line(f"GoGoDownloader R2 v{version.__version__}")
    preprint.define_alignment(tabs=1)
    preprint.add_tab(lines=33)
    preprint.add_sort(key="1",value="Search at Homepage", separator=".)")
    preprint.add_sort(key="2",value="Search by Genres", separator=".)")
    preprint.add_line("Or type in the title, to search")
    preprint.add_tab(lines=33)
    preprint()
    selection = user_input("\tEnter Number/Search title:", [1,2,"any"])
    print("\tLoading (restart if it took >10s)")
    if selection == 1:
        return ResultZone("Home")
    elif selection == 2:
        return ResultZone("Genre")
    else:
        return ResultZone("Search", value=selection)

def mainwithargs():
    parser = argparse.ArgumentParser(description='GoGoDownloader R2 v{version.__version__}')

    # Subparsers for different commands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search for anime titles')
    search_parser.add_argument('query', type=str, help='Search query')

    # Download command
    download_parser = subparsers.add_parser('download', help='Download anime episodes')
    download_parser.add_argument('--query', type=str, help='Search query')
    download_parser.add_argument('--index', type=int, help='Index of the title to download')
    download_parser.add_argument('--start-ep', type=int, help='Start episode number')
    download_parser.add_argument('--end-ep', type=int, help='End episode number (optional)')

    args = parser.parse_args()
    endepisode = args.end_ep

    if args.command == 'search':
        search_result = ResultZone("Search", value=args.query)
        if search_result == 1:
            print("No search result found")
            return

        # Display all search results and allow the user to choose one
        print("Search Results:")
        for i, result in enumerate(search_result, start=1):
            print(f"{i}. {result}")
        selected_index = user_input("Select a search result by index:", valid=[i for i in range(1, len(search_result) + 1)])
        selected_result = search_result[selected_index - 1]

        if endepisode is None:
            goepisode = EpisodeScraper(selected_result)
            available_episodes = goepisode.get_episodes()
            endepisode = available_episodes

        return Episode_UI(selected_result, anime_title=args.query, starting_ep=args.start_ep, ending_ep=args.end_ep)

    elif args.command == 'download':
        if args.query is None or args.index is None or args.start_ep is None:
            print("Error: All required arguments (--query, --index, --start-ep) must be provided for the download command.")
            return
        print("reached the result zone")
        if args.index is not None:
            indexspecified = True
        else :
            indexspecified = False

        search_result = ResultZone("Search", value=args.query, indexspecified = indexspecified , index=args.index)
        print("passed the result zone")
        if search_result == 1:
            print("No search result found")
            return

        if endepisode is None:
            print("reached line 2")
            goepisode = EpisodeScraper(search_result[args.index - 1])
            available_episodes = goepisode.get_episodes()
            endepisode = available_episodes

        return Episode_UI(search_result[args.index - 1], anime_title=args.query, starting_ep=args.start_ep, ending_ep=args.end_ep)


def update_checker():
    prettify = Prettify()
    prettify.add_tab("Update Notice",lines=50, char='-')
    version.init()
    notification = version.show_update(prettify=prettify)
    prettify.add_tab(lines=50, char='-')
    if (notification):
        prettify()



if __name__ == "__main__":
    update_checker()
    if len(sys.argv) > 1:
        mainwithargs()
    else:
        main()