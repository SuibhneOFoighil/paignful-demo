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
from node import YTVideo, is_null, NULL_ID

load_dotenv()
openai.api_key = os.environ.get('OPENAI_API_KEY')
YT_api_key = os.environ.get('YOUTUBE_API_KEY')
PINECONE_API_KEY = os.environ.get('PINECONE_API_KEY')
PINECONE_ENV = os.environ.get('PINECONE_ENV')

def get_embedding(text, model="text-embedding-ada-002"):
   text = text.replace("\n", " ")
   return openai.Embedding.create(input = [text], model=model)['data'][0]['embedding']

# Define a function that takes seconds as an input and returns a string in '00:00:00' or '00:00' format
def convert_seconds(seconds):
    # Check if the input is a positive integer
    if isinstance(seconds, int) and seconds >= 0:
        # Calculate the hours, minutes and seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = (seconds % 3600) % 60
        # Format the output as '00:00:00' or '00:00'
        if hours > 0:
            output = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            output = f"{minutes:02d}:{seconds:02d}"
        return output
    else:
        # Return an error message if the input is invalid
        return "Invalid input. Please enter a positive integer."
   
"""returns Kx3 matrix of metadata, where rows are initially queried nodes,
and columns are their 'related' (previous and next) children.
the left or right spots will be filled with the NULL_ID
if the queried node is the first or last in a video"""
def recursive_query(db, query, K=2):
  xq = get_embedding(query)
  res = db.query([xq], top_k=K, include_metadata=True)
  matches = res['matches']

  # [ prev_1, id_1, next_1 ]
  # [ prev_2, id_2, next_2 ]
  # [... for k queries ]
  query_nodes = [
      [
          item['metadata']['prev'],
          item['id'],
          item['metadata']['next']
      ] for item in matches
  ]

  fetch_response = [ db.fetch(ids=node_ids) for node_ids in query_nodes ]
  query_vectors = [ res['vectors'] for res in fetch_response ]

  #HANDLE NULL VALUES...
  query_metadatas = [
      [
          query_vectors[i][id]['metadata'] if not is_null(id) else NULL_ID for id in node_set
      ] for i, node_set in enumerate(query_nodes)
  ]

  return query_metadatas

def format_context_matrix(mat):
  formatted_queries = []
  for i, query in enumerate(mat):
    txt = [ node['transcript'] for node in query if not is_null(node) ]
    center_node = query[1]
    video_id = center_node['video_id']
    # title = center_node['title']
    # creation_date = center_node['created']
    timestamp = int(center_node['timestamp'])
    # readable_timestamp = convert_seconds(timestamp)
    citation = f"({i+1})"
    formatted_nodes = '\n'.join(txt)
    formatted_query = f'{citation}: {formatted_nodes}'
    formatted_queries.append(formatted_query)
  return '\n\n'.join(formatted_queries)

def get_citations(mat):
    citations = []
    for i, query in enumerate(mat):
        center_node = query[1]
        video_id = center_node['video_id']
        timestamp = int(center_node['timestamp'])
        number = i+1
        url = f'https://www.youtube.com/watch?v={video_id}&t={timestamp}'
        citations.append((number, url))
    return citations

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

    # iterate over data and create YTVideo objects
    print('Creating YTVideo objects...')
    ytvids = []
    iterable = zip(video_ids, transcripts, titles, creation_dates)
    for video_id, transcript, title, creation_date in iterable:
        ytvid = YTVideo(video_id, transcript, title, creation_date)
        ytvids.append(ytvid)

    #store YTVideo objects as pickle
    print('Storing YTVideo objects...')
    with open('./vivek_embeds/vivek_ytvids.pkl', 'wb') as f:
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