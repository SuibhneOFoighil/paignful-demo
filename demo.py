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

def get_time_buying_response():
    statements = [
        "Hmm, that's a really thoughtful question. Let me ponder this for a moment.",
        "You raise a good point. I'd like to give this some careful consideration before responding.",
        "That's an interesting perspective. Give me a minute to wrap my head around it.",
        "I appreciate you sharing that viewpoint. I'll need to reflect on it before crafting a thoughtful response.",
        "Let me make sure I fully understand what you're asking before jumping to any conclusions.",
        "You've given me something meaningful to mull over. I don't want to respond prematurely.",
        "I want to be sure I'm grasping all the nuances here. Please give me a few minutes to think this through.",
        "You've challenged my assumptions - let me step back and reevaluate my thinking on this.",
        "I need some time to digest what you've said and consider it from multiple angles.",
        "These are weighty ideas that warrant careful rumination. I don't want to respond superficially.",
        "I need to turn this over in my mind a bit before articulating a response. Please bear with me.",
        "Let me reflect on this for a bit - I want to give your perspective the consideration it deserves.", 
        "Hmm, I'll need to ponder the implications of what you're saying. Just a moment please.",
        "You've given me a lot to chew on! I don't want to jump in hastily.",
        "I appreciate you bringing this issue to my attention. Let me take some time to deliberate.",
        "I want to be thoughtful and not reactive. Please allow me a few minutes to contemplate your words.",
        "Let me take a beat to truly absorb the spirit of your question. I'll get back to you shortly.",
        "I'd like to approach this with care and nuance. Please give me a some time to formulate my response.",
        "You raise critical questions - let me hold them in my mind before crafting a measured reply.",
        "I don't want to risk trivializing your perspective. Please grant me a short time to consider the best way forward."
    ]

    return random.choice(statements)

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
    pattern = r'\*\*((\(\d+\))+)\*\*'
    stripped_text = re.sub(pattern, '', text)
    pattern = r'\(\d+\)'
    stripped_text = re.sub(pattern, '', stripped_text)
    return stripped_text

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

def stream_audio(response, strip):
    to_speak = strip_citations(response) if strip else response
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
    recording = stream(audio_stream)
    return recording

# output text 
def display_transcription(output_text, placeholder):
    full_response = '#### Transcript \n\n'
    placeholder.markdown(full_response)
    # Simulate stream of response with milliseconds delay
    for chunk in output_text.split():
        full_response += chunk + " "
        time.sleep(0.02)
        # Add a blinking cursor to simulate typding
        placeholder.markdown(full_response + "▌")
    placeholder.markdown(full_response)
    return full_response

def display_message(message):
    with st.chat_message(message["role"], avatar=message.get('avatar', None)):
        if message["role"] == "assistant":
            st.audio(message["audio"])
            st.markdown("#### Transcript")
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
    If you reference the quotes, always cite them individually and in bold within your response, like so: 'I have always supported dogs - **(1)(2)**.'
    
    % User Profile %
    Adapt your response to the user profile: "{st.session_state.personalization['who']}"

    % Response Length %
    Limit your response to {st.session_state.personalization['length']} words

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

    # return response and citations
    print(response.choices[0])
    response_text = response.choices[0]["message"]["content"]
    return response_text, citations

if __name__ == "__main__":

    # Set page title
    st.title("Vivek Ramaswamy's AI Profile")
    st.write('Powered by [Molus](https://molus.app)🔺 | Contact: suibhne@molus.app')

    # Setup personalization parameters
    if "personalization" not in st.session_state:
        st.session_state.personalization = {
            "who": "My name is Ian. I'm a farmer from Iowa. I'm pro-gun, pro-abortion, and worried about the economy.",
            "length": "200 words",
            "simplification": False
        }
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    with st.sidebar:
        st.header("Personalization")
        st.session_state.personalization['who'] = st.text_area("Who are you?", "My name is Ian. I'm a farmer from Iowa. I'm pro-gun, pro-abortion, and worried about the economy.")
        st.session_state.personalization['length'] = st.slider("Response length", 50, 500, 100)
        st.session_state.personalization['simplification'] = st.checkbox("Speak to me like I'm 5")

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        display_message(message)

    # Accept user input
    if prompt := st.chat_input("What is up?"):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        # Display user message in chat message container
        with st.chat_message("user"):
            st.markdown(prompt)

        # Display assistant response in chat message container
        with st.chat_message("assistant", avatar=PROFILE_PIC):
            
            audio_placeholder = st.empty()
            transcription_placeholder = st.empty()
            citation_placeholder = st.empty()
            status_placeholder = st.empty()

            status = status_placeholder.status("Processing...", expanded=True)

            # Read time buying response
            time_buying_response = get_time_buying_response()
            try:
                audio_response = stream_audio(time_buying_response, strip=False)
            except (BrokenPipeError, IOError):
                print("Audio stream failed")
                print(BrokenPipeError)
                print(IOError)
                st.error("Audio stream failed")
            # stream_audio(time_buying_response, strip=False)
            
            # Give the model some time to think
            status.write("Gathering thoughts...")
            assistant_response, all_citations = get_response(prompt)

            # FOR DEBUGGING AUDIO
            # assistant_response = "Hello Ian, thank you for reaching out. I understand that you are a farmer from Iowa and you have concerns about the economy. I believe in transparency, openness, free speech, and open debate as the way forward. We need to address the issues that led to the current state of our economy. As I have always said, nobody is coming from on high to save us in politics. It is up to us to save ourselves and choose a national revival over national division. Let's work together to restore the heart and soul of this country. Thank you for your input, Ian."
            # # stream_audio(full_response)
            
            # Respond with model response
            status.write('Responding to you...')
            try:
                audio_response = stream_audio(assistant_response, strip=True)
                audio_placeholder.audio(audio_response)
            except (BrokenPipeError, IOError):
                print("Audio stream failed")
                print(BrokenPipeError)
                print(IOError)
                st.error("Audio stream failed")

            # Stream transcribed response 
            status.write('Transcribing response...')
            display_transcription(assistant_response, transcription_placeholder)

            # Display citations
            used_numbers = extract_reference_numbers(assistant_response)
            used_citations = [ citation for citation in all_citations if citation[0] in used_numbers ]
            citations = list(zip(*used_citations))
            # citations = [[1], ['https://www.youtube.com/watch?v=7eJUMRyNev4&t=430']]
            display_citations(citations, citation_placeholder)

            # Close status bar
            status_placeholder.empty()

        # Add assistant response to chat history
        st.session_state.messages.append({
            "key": len(st.session_state.messages),
            "role": "assistant", 
            "content": assistant_response, 
            'avatar': PROFILE_PIC,
            'citations': citations,
            'audio': audio_response
        })

