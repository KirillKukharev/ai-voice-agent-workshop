DEFAULT_BARGE_IN_FRAMES = 8
DEFAULT_COMMIT_GAP_SECONDS = 2.0  # Увеличено с 0.5 сек до 2.0 сек для длинных пауз между словами
BARGE_IN_GRACE_SECONDS = 0.4
BARGE_IN_VAD_THRESHOLD = 0.5
START_VAD_THRESHOLD = 0.8  # Порог для начала распознавания

PRE_ROLL_MS = 120
POST_ROLL_MS = 180

MAX_UTTERANCE_SECONDS = 15.0  # Увеличено с 6 до 15 сек для очень длинных реплик
MIN_UTTERANCE_SECONDS = 0.4

BYTES_PER_FRAME_8K = 160
BYTES_PER_FRAME_16K = 320

AST_APP = "voice-bot"
FRAME_MS = 20

AST_HOST = "asterisk"
AST_PORT = 5039

AST_USER = "ariuser"
AST_PASS = "changeme"

OUTPUT_CODEC = "g722"
SAMPLE_RATE = 16000

FIRST_PROMPT_AFTER_S = 10.0  # если пользователь ещё не говорил
REPROMPT_AFTER_S = 8.0  # Увеличено с 5.0 сек до 8 сек паузы перед повторным вопросом
HANGUP_AFTER_S = 10.0  # после вопроса ещё 10с тишины — завершаем

# Audio codec payload types (RTP)
PAYLOAD_TYPE_ULAW = 0  # G.711 μ-law
PAYLOAD_TYPE_ALAW = 8  # G.711 A-law
PAYLOAD_TYPE_G722 = 9  # G.722

# Sample rates
SAMPLE_RATE_8K = 8000
SAMPLE_RATE_16K = 16000

# Timing constants
JITTER_BUFFER_GAP_THRESHOLD_MS = 0.03  # gap > 30ms suggests lost frames
CDR_ANSWER_DELAY_SECONDS = 2  # Answer delay for CDR records

MAX_DIALOG_HISTORY = 10

SPEECH_FRAMES_THRESHOLD = 4
MAX_SILENCE_DURATION = 5.0  # Увеличено с 1.2 сек до 5.0 сек для очень длинных пауз между словами
SILENCE_FRAMES_THRESHOLD = 25  # Уменьшено с 50 кадров до 25 кадров (1000ms = 1 сек)


CHANNELS = 1

TTS_SYNTH_TIMEOUT_MS = 3000

GREETING_AI_BOT_TEXT = "Добрый день! Чем я могу вам помочь?"
FALLBACK_AI_BOT_TEXT = "Я вас не поняла, пожалуйста повторите."
QUESTION_AI_BOT_TEXT = "Желаете что-нибудь спросить или узнать?"
QUESTION_ABOUT_QUESTION_AI_BOT_TEXT = "Остались ли у вас ещё вопросы?"
