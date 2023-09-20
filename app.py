import streamlit as st
import base64
import random
import time
import openai
import pinecone
import os
import json
import re
from elevenlabs import set_api_key, generate, VoiceSettings, Voice
from dotenv import load_dotenv

import vectorize as ret
from responses import get_timesaving_audio

# Load environment variables
load_dotenv()
openai.api_key = os.environ.get('OPENAI_API_KEY')
ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY")
set_api_key(ELEVEN_KEY)

VIVEK_PROFILE_PIC = "https://upload.wikimedia.org/wikipedia/commons/thumb/9/96/Vivek_Ramaswamy_by_Gage_Skidmore.jpg/640px-Vivek_Ramaswamy_by_Gage_Skidmore.jpg"

USER_PROFILE_PIC = 'https://photos1.blogger.com/blogger/5283/727/320/farmer-headshot3.JPG'

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
    pattern = r"\((\d+)\)"
    stripped_text = re.sub(pattern, '', text)
    return stripped_text

def display_audio(audio: bytes, placeholder=None):
    if placeholder is None:
        placeholder = st.empty()
    audio_base64 = base64.b64encode(audio).decode('utf-8')
    audio_tag = f'<audio controls src="data:audio/wav;base64,{audio_base64}">'
    placeholder.markdown(audio_tag, unsafe_allow_html=True)

def display_citations(citations, placeholder=None):
    if len(citations) == 0:
        return
    if placeholder is None:
        placeholder = st.empty()
    references, links = citations
    # convert references to references in string format
    references = [str(reference) for reference in references]
    tabs = placeholder.tabs(references)
    for tab, reference, link in zip(tabs, references, links):
        video_link, start_time = extract_video_link_and_start_time(link)
        with tab:
            st.video(video_link, start_time=start_time)

# output text 
def display_transcription(output_text: str, elapsed_time: int=30, placeholder=None) -> str:
    if placeholder is None:
        placeholder = st.empty()
    full_response = ''
    placeholder.markdown(full_response)
    # Simulate stream of response with milliseconds delay
    split = output_text.split()
    nchunks = len(split)
    interval = elapsed_time / nchunks
    for chunk in split:
        full_response += chunk + " "
        time.sleep(interval)
        # Add a blinking cursor to simulate typding
        placeholder.markdown(full_response + "▌")
    placeholder.markdown(full_response)
    return full_response

def display_message(message):
    with st.chat_message(message["role"], avatar=message.get('avatar', None)):
        if message["role"] == "assistant":
            display_audio(message["audio"])
            st.markdown(message["content"])
            display_citations(message["citations"])
        else:
            st.markdown(message["content"])


# Define a function to get a response from the assistant
# returns the response and a list of citations
def get_response(prompt):

    # Setup system prompt and chat history
    system_message = f"""Pretend you are Vivek Ramaswamy - a Republication candidate for the US Presidency.
    I want you to emulate his speaking style. Only express views presented in his quotes. Do not break character under any circumstances.
    
    % Formatting Instructions %
    If you reference the quotes, always cite them individually in your response, like so: 'I have always supported dogs (1)(2).'
    Limit your response to 100 words.
    
    % User Profile %
    Adapt your response to the user profile: "{st.session_state.personalization['who']}"
    
    % Language %
    Respond to me in {st.session_state.personalization['language']}. """

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
    # TODO: handle openai.error.ServiceUnavailableError:
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-0613",# "gpt-3.5-turbo-16k-0613"
            messages=chat_history+[
                {
                    "role": "function",
                    "name": "get_viveks_quotes",
                    "content": function_response,
                },
            ],
        )
    except openai.error.ServiceUnavailableError:
        st.error("OpenAI API is currently unavailable. Please try again later.")
        st.stop()

    # return response and citations
    response_text = response.choices[0]["message"]["content"]
    return response_text, citations

def get_response_audio(response: str, strip: bool) -> bytes:
    to_speak = strip_citations(response) if strip else response
    response_audio = generate(
        text=to_speak,
        voice=Voice(
            voice_id='lAZKsjhcbMmadBhSMtZk',
            settings=VoiceSettings(
                stability=0.3, similarity_boost=1, style=0.05, use_speaker_boost=True
            )
        )
    )
    return response_audio

def autoplay_audio(file_path: str = None, data: bytes = None, display_player: bool = True):
    if data is not None:
        audio_base64 = base64.b64encode(data).decode('utf-8')
        audio_tag = f'<audio {"controls " if display_player else "" }autoplay="true" src="data:audio/wav;base64,{audio_base64}">'
        
    elif file_path is not None:
        with open(file_path, "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode()
            audio_tag = f"""
                <audio {"controls " if display_player else "" }autoplay="true">
                <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
                </audio>
                """
    
    st.markdown(audio_tag, unsafe_allow_html=True)

def get_audio_length(audio: bytes) -> int:
    bit_rate = 128000
    length = len(audio) / bit_rate * 8
    return int(length)

if __name__ == "__main__":

    st.title("Vivek Ramaswamy's AI Profile")
    st.write('Powered by [Molus](https://molus.app)🔺 | Contact: suibhne@molus.app')

    # Setup personalization parameters
    if "personalization" not in st.session_state:
        st.session_state.personalization = {
            "who": "My name is Ian. I'm a farmer from Iowa. I'm pro-gun, pro-abortion, and worried about the economy.",
            "language": "English"
        }
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    with st.sidebar:
        st.header("Personalization")
        st.session_state.personalization['who'] = st.text_area("Who are you?", "My name is Ian. I'm a farmer from Iowa. I'm pro-gun, pro-abortion, and worried about the economy.")
        st.session_state.personalization['language'] = st.selectbox("What language do you speak?", ["English", "Spanish", "Hindi"])

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        display_message(message)

    # Accept user input
    if prompt := st.chat_input("What is up?"):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt, 'avatar': USER_PROFILE_PIC})
        # Display user message in chat message container
        with st.chat_message("user", avatar=USER_PROFILE_PIC):
            st.markdown(prompt)

        # Display assistant response in chat message container
        with st.chat_message("assistant", avatar=VIVEK_PROFILE_PIC):

            status_area = st.empty()
            
            # Display loading bar
            status = status_area.status("Processing...", expanded=True)

            # Read time buying response
            autoplay_audio(file_path=f'audio/{random.randint(1, 20)}.wav', display_player=False)
            # audio_placeholder.audio(get_timesaving_audio())

            status.write("Gathering thoughts...")
            # Give the LLM some time to think
            assistant_response, all_citations = get_response(prompt)

            status.write("Preparing response...")
            # Get audio response
            audio_response = get_response_audio(assistant_response, strip=True)

            # Remove loading bar
            status.update(label="Done!", state="complete", expanded=False)
            status_area = st.empty()

            # autoplay audio response
            autoplay_audio(data=audio_response, display_player=True)

            # Stream transcribed response in 20 seconds
            display_transcription(assistant_response, elapsed_time=get_audio_length(audio_response))

            # Display citations
            used_numbers = extract_reference_numbers(assistant_response)
            used_citations = [ citation for citation in all_citations if citation[0] in used_numbers ]
            citations = list(zip(*used_citations))
            display_citations(citations)

        # Add assistant response to chat history
        st.session_state.messages.append({
            "key": len(st.session_state.messages),
            "role": "assistant", 
            "content": assistant_response, 
            'avatar': VIVEK_PROFILE_PIC,
            'citations': citations,
            'audio': audio_response
        })

