import random
import os
from dotenv import load_dotenv
from elevenlabs import set_api_key, generate, VoiceSettings, Voice, save

STATEMENTS = [
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
N_STATEMENTS = len(STATEMENTS)

def generate_audio(txt: str) -> bytes:
    return generate(
        text=txt,
        voice=Voice(
            voice_id='lAZKsjhcbMmadBhSMtZk',
            settings=VoiceSettings(
                stability=0.3, similarity_boost=1, style=0.05, use_speaker_boost=True
            )
        )
    )

def get_timesaving_audio() -> bytes:
    #pick random number between 1 and N_STATEMENTS
    idx = random.randint(1, N_STATEMENTS)
    #load audio from file
    path = f"audio/{idx}.wav"
    with open(path, "rb") as f:
        audio = f.read()
    return audio

if __name__ == '__main__':

    load_dotenv()

    # Load environment variables
    api_key = os.environ.get('ELEVENLABS_API_KEY')
    set_api_key(api_key)

    for i, statement in enumerate(STATEMENTS):
        print(f"Generating audio for statement {i+1} of {len(STATEMENTS)}")
        audio = generate_audio(statement)
        path = f"audio/{i+1}.wav"
        save(audio, path)