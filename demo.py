import streamlit as st
import random
import time
import openai
import pinecone
import os
import json
import re
from elevenlabs import set_api_key, generate, stream, VoiceSettings, Voice
from dotenv import load_dotenv

import vectorize as ret

# Load environment variables
load_dotenv()
openai.api_key = os.environ.get('OPENAI_API_KEY')
ELEVEN_KEY = os.environ.get("ELEVEN_KEY")
set_api_key(ELEVEN_KEY)

PROFILE_PIC = "https://upload.wikimedia.org/wikipedia/commons/thumb/9/96/Vivek_Ramaswamy_by_Gage_Skidmore.jpg/640px-Vivek_Ramaswamy_by_Gage_Skidmore.jpg"

# Initialize Pinecone index
pinecone.init(
    api_key=os.environ.get('PINECONE_API_KEY'),
    environment=os.environ.get('PINECONE_ENV')
)
index_name = 'vivek-demo-v1'
INDEX = pinecone.Index(index_name)

def extract_reference_numbers(text):
    pattern = r"\((\d+)\)"
    matches = re.findall(pattern, text)
    references = [int(match[0]) for match in matches]
    return references

def extract_video_link_and_start_time(url):
    result = url.split('&t=')
    video_link = result[0]
    start_time = int(result[1]) if len(result) > 1 else 0
    return video_link, start_time

def strip_citations(text) -> str:
    #TODO: DOES THIS RETURN A GENERATOR OBJECT??
    pattern = r'\*\*\((\d+)\)\*\*'
    stripped_text = re.sub(pattern, '', text)
    return stripped_text

def display_citations(citations):
    if len(citations) == 0:
        return
    references, links = citations
    # convert references to references in string format
    references = [str(reference) for reference in references]
    tabs = st.tabs(references)
    for tab, reference, link in zip(tabs, references, links):
        video_link, start_time = extract_video_link_and_start_time(link)
        with tab:
            st.video(video_link, start_time=start_time)

def stream_audio(response):
    to_speak = strip_citations(response)
    audio_stream = generate(
        text=to_speak,
        voice=Voice(
            voice_id='lAZKsjhcbMmadBhSMtZk',
            settings=VoiceSettings(
                stability=0.3, similarity_boost=1, style=0.05, use_speaker_boost=True
            )
        ),
        stream=True
    )
    stream(audio_stream)

# Define a function to get a response from the assistant
# returns a stream of responses from the model, and a list of citations
def get_response_stream(prompt):

    # Setup system prompt and chat history
    system_message = f"""Pretend you are Vivek Ramaswamy - a Republication candidate for the US Presidency.
    I want you to emulate his speaking style. Only express views presented in his quotes. Do not break character under any circumstances.
    
    % Formatting Instructions %
    If you reference the quotes, always cite them in bold within your response, like so: 'I have always supported dogs - **(1)**.'
    
    % User Profile %
    Adapt your response to the user profile: "{st.session_state.personalization['who']}"

    % Response Length %
    {st.session_state.personalization['length']}

    % Simplification %
    {"speak to me like I'm 5" if st.session_state.personalization['simplification'] else ""}
    """
    system_prompt = {
        "role": "system",
        "content": system_message
    }

    # format st session state messages into openai format
    messages_openai_format = [
        {'role': message['role'], 'content': message['content']} for message in st.session_state.messages
    ]
    chat_history = [system_prompt] + messages_openai_format

    # get function response
    K = 5
    X = ret.recursive_query(INDEX, prompt, K)
    function_response = ret.format_context_matrix(X)
    citations = ret.get_citations(X)

    # send model the info on the function call and function response
    stream = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-16k-0613", #"gpt-4-0613"
        stream=True,
        messages=chat_history+[
            {
                "role": "function",
                "name": "get_viveks_quotes",
                "content": function_response,
            },
        ],
    )

    return stream, citations

if __name__ == "__main__":

    # Set page title
    st.title("Vivek Ramaswamy")

    # Setup personalization parameters
    if "personalization" not in st.session_state:
        st.session_state.personalization = {
            "who": "My name is Ian. I'm a farmer from Iowa. I'm pro-gun, pro-abortion, and worried about the economy.",
            "length": "1 paragraph",
            "simplification": False
        }
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    with st.sidebar:
        st.header("Personalization")
        st.session_state.personalization['who'] = st.text_area("Who are you?", "My name is Ian. I'm a farmer from Iowa. I'm pro-gun, pro-abortion, and worried about the economy.")
        st.session_state.personalization['length'] = st.selectbox('Response Length', ['1 paragraph', '3 paragraphs', '5 paragraphs'])
        st.session_state.personalization['simplification'] = st.checkbox("Speak to me like I'm 5")

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"], avatar=message.get('avatar', None)):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                #display play button
                if st.button("Listen to me!", key=message["key"]):
                    stream_audio(message["content"])
                #display citations
                display_citations(message["citations"])

    # Accept user input
    if prompt := st.chat_input("What is up?"):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        # Display user message in chat message container
        with st.chat_message("user"):
            st.markdown(prompt)

        # Display assistant response in chat message container
        with st.chat_message("assistant", avatar=PROFILE_PIC):
            message_placeholder = st.empty()
            full_response = ""

            # FOR DEBUGGING AUDIO
            full_response = "Hello Ian, thank you for reaching out. I understand that you are a farmer from Iowa and you have concerns about the economy. I believe in transparency, openness, free speech, and open debate as the way forward. We need to address the issues that led to the current state of our economy. As I have always said, nobody is coming from on high to save us in politics. It is up to us to save ourselves and choose a national revival over national division. Let's work together to restore the heart and soul of this country. Thank you for your input, Ian."
            # stream_audio(full_response)
            all_citations = [[1, 'https://www.youtube.com/watch?v=1X7fZoDs9KU&t=0s']]
            message_placeholder.markdown(full_response) 
    
            # stream, all_citations = get_response_stream(prompt)
            # for response in stream:
            #     full_response += response.choices[0].delta.get("content", "")
            #     # Add a blinking cursor to simulate typing
            #     message_placeholder.markdown(full_response + "▌")
            # message_placeholder.markdown(full_response)
  
            # display play button
            if st.button("Listen to me!", key=len(st.session_state.messages)) and len(full_response) > 0:
                stream_audio(full_response)

            # Display citations
            used_numbers = extract_reference_numbers(full_response)
            used_citations = [ citation for citation in all_citations if citation[0] in used_numbers ]
            citations = list(zip(*used_citations))
            display_citations(citations)

        # Add assistant response to chat history
        st.session_state.messages.append({
            "key": len(st.session_state.messages),
            "role": "assistant", 
            "content": full_response, 
            'avatar': PROFILE_PIC,
            'citations': citations
        })

