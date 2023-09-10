# Purpose: upsert data into database

# import libraries
import csv
import os
import random
import openai
import pinecone
import pickle
from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from dotenv import load_dotenv
from tqdm import tqdm

from node import YTVideo

load_dotenv()
openai.api_key = os.environ.get('OPENAI_API_KEY')
YT_api_key = os.environ.get('YOUTUBE_API_KEY')
PINECONE_API_KEY = os.environ.get('PINECONE_API_KEY')
PINECONE_ENV = os.environ.get('PINECONE_ENV')


def get_embedding(text, model="text-embedding-ada-002"):
   text = text.replace("\n", " ")
   return openai.Embedding.create(input = [text], model=model)['data'][0]['embedding']

if __name__ == '__main__':

    print('Starting upsert.py...')
    #read in csv
    with open('./vivek_embeds/vivek_video_ids.txt') as f:
        reader = csv.reader(f)
        all_video_ids = [ row[0] for row in reader ]

    #get transcript for each video_id
    print('Getting transcripts...')
    result = YouTubeTranscriptApi.get_transcripts(
        video_ids=listvideo_ids,
        languages=['en', 'en-US'],
        continue_after_error=True
    )

    # extract data from result
    print('Extracting data...')
    items = [ (video_id, transcript) for video_id, transcript in result[0].items() ]
    video_ids, transcripts = zip(*items)

    #get title for each video_id
    youtube = build('youtube', 'v3', developerKey=YT_api_key)

    # Get the video details from YouTube Data API
    print('Getting video details...')
    video_details = []
    for i in range(0, len(video_ids), 50):
        video_batch = youtube.videos().list(
            part='snippet',
            id=','.join(video_ids[i:i+50])
        ).execute()
        video_details.extend(video_batch['items'])
    print('Extracting video details...')
    items = [ 
        (item['snippet']['title'], item['snippet']['publishedAt']) 
        for item in video_details 
    ]
    titles, creation_dates = zip(*items)

    # # store video_ids, titles, creation_dates as csv
    # print('Storing video details...')
    # with open('./vivek_embeds/vivek_video_ids_titles_dates.csv', 'w') as f:
    #     writer = csv.writer(f)
    #     writer.writerow(['video_id', 'title', 'creation_date'])
    #     writer.writerows(zip(video_ids, titles, creation_dates))

    # iterate over data and create YTVideo objects
    print('Creating YTVideo objects...')
    ytvids = []
    iterable = zip(video_ids, transcripts, titles, creation_dates)
    for video_id, transcript, title, creation_date in iterable:
        ytvid = YTVideo(video_id, transcript, title, creation_date)
        ytvids.append(ytvid)

    #store YTVideo objects as pickle
    print('Storing YTVideo objects...')
    with open('./vivek_embeds/vivek_ytvids-2.pkl', 'wb') as f:
        pickle.dump(ytvids, f)
    
    # OPTIONAL LINE: read in YTVideo objects from pickle
    # with open('./vivek_embeds/vivek_ytvids.pkl', 'rb') as f:
    #     ytvids = pickle.load(f)

    #create index
    print('Creating index...')
    index_name = 'vivek-demo-v1'
    pinecone.init(
        api_key=PINECONE_API_KEY,
        environment=PINECONE_ENV
    )

    index = pinecone.Index(index_name)

    #upsert data for each video
    print('Upserting data...')
    for vid in tqdm(ytvids):
        texts = vid.get_chunk_transcripts()
        metadatas = vid.get_chunk_metadatas()
        ids = vid.get_chunk_ids()

        #TODO: change to title + created time + transcript + timestamp embedding
        embeds = [ get_embedding(t) for t in texts ]

        for i, md in enumerate(metadatas):
            md['transcript'] = texts[i]

        to_upsert = zip(ids, embeds, metadatas)

        upsert_response = index.upsert(
            vectors=to_upsert
        )