from json.decoder import JSONDecodeError
from langchain.llms import OpenAIChat
from llama_index import Document, GPTSimpleVectorIndex, LLMPredictor, PromptHelper
from llama_index.langchain_helpers.chatgpt import ChatGPTLLMPredictor
from llama_index.prompts.chat_prompts import CHAT_REFINE_PROMPT
from openai import ChatCompletion
from openai.error import InvalidRequestError, RateLimitError
from tenacity import RetryError
import asyncio, json, math, os, re, sys, tiktoken, time, yaml

SYSTEM_MESSAGE = {"role": "system", "content": "You are a researcher who answers only in JSON arrays, no plaintext, without whitespace. Identify the susceptibility factors present in the document. Identify the source, nature of the relationship, and target. The only valid relationships are \"promotes\" and \"inhibits\". If you don't know any answers, write the empty array []. Example response: " + '[ { "source": "CEBPE gene promoter polymorphism (rs2239630 G > A)", "relationship": ["promotes"], "target": "B-cell acute lymphoblastic leukemia" } ]\n'}

def create_or_update(index, doc):
  if index.docstore.document_exists(doc.doc_id):
    index.update(doc)
  else:
    index.insert(doc)

def num_tokens_from_messages(messages, model="gpt-3.5-turbo-0301"):
  """Returns the number of tokens used by a list of messages."""
  try:
      encoding = tiktoken.encoding_for_model(model)
  except KeyError:
      encoding = tiktoken.get_encoding("cl100k_base")
  if model == "gpt-3.5-turbo-0301":  # note: future models may deviate from this
      num_tokens = 0
      for message in messages:
          num_tokens += 4  # every message follows <im_start>{role/name}\n{content}<im_end>\n
          for key, value in message.items():
              num_tokens += len(encoding.encode(value))
              if key == "name":  # if there's a name, the role is omitted
                  num_tokens += -1  # role is always required and always 1 token
      num_tokens += 2  # every reply is primed with <im_start>assistant
      return num_tokens
  else:
      raise NotImplementedError(f"""num_tokens_from_messages() is not presently implemented for model {model}.
  See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens.""")

def index_doc(index, doc, answers):
  gi_answers = [answer['data']['answer'] for answer in answers]
  gi_doc = 'Answers:' + json.dumps(gi_answers, separators=(',', ':')) + '\nDocument: ' + json.dumps(doc, separators=(',', ':'))
  create_or_update(index, Document(gi_doc, doc_id=doc['hash']))
  return index

def query(index, llm_predictor, prompt_helper, prompt):
  messages = [
    SYSTEM_MESSAGE,
    {"role": "user", "content": prompt}
  ]

  #tokens = prompt_helper._tokenizer(prompt)
  tokens = num_tokens_from_messages(messages)
  #print('size', prompt_helper.max_input_size, len(tokens), prompt_helper.get_chunk_size_given_prompt(prompt, 1), prompt_helper._tokenizer)
  #if len(tokens) >= prompt_helper.max_input_size:
  if tokens >= 3071:
    reduction_ratio = prompt_helper.max_input_size / tokens
    reduced_prompt_length = int(len(prompt) * (1 - reduction_ratio)) - 1
    prompt = prompt[:reduced_prompt_length]
    return query(index, llm_predictor, prompt_helper, prompt)
  else:
    return ChatCompletion.create(
          model="gpt-3.5-turbo-0301", messages=messages
      )
    #return index.query(prompt, llm_predictor=llm_predictor, prompt_helper=prompt_helper, refine_template=CHAT_REFINE_PROMPT, similarity_top_k=3)

def completions_to_answers(predictions, label):
  label_order = label['json-schema']['items']['srvcOrder']
  content = predictions['choices'][0]['message']['content'].strip()
  finish_reason = predictions['choices'][0]['finish_reason']
  if finish_reason == 'stop':
    try:
      raw_answers = json.loads(content)
    except JSONDecodeError:
      # Sometimes gpt-3.5 returns a prose answer stating that it has no answers
      return []
  elif finish_reason == 'length':
    # JSON truncated
    return []
  else:
    # No API response, or content omitted due to filters
    return []

  answers = []
  for row in raw_answers:
    answers.append({
      label_order[0]: row['source'],
      label_order[1]: row['relationship'],
      label_order[2]: row['target'],
    })
  return answers

def predict_doc(index, llm_predictor, prompt_helper, doc, label):
  json_schema = '{"$id":"http://localhost:4061/web-api/srvc-json-schema?hash=QmQ4djRUAv7QmKL5KSZ3ZfvhRBBqgxcLjHyzXXf6uA4wVZ","type":"array","items":{"type":"object","srvcOrder":["stringwgdddI","categoricalLfOFUj","stringWODblq"],"properties":{"stringWODblq":{"type":"string","title":"Target","maxLength":100},"stringwgdddI":{"type":"string","title":"Source","maxLength":100},"categoricalLfOFUj":{"type":"array","items":{"enum":["inhibits","promotes"],"type":"string"},"title":"Relationship"}}},"title":"Relationships","$schema":"http://json-schema.org/draft-07/schema"}'
  # This prompt works well for GPT-4
  #prompt = "You are a researcher who answers only in JSON that is valid according to this schema:" + json_schema + ". Identify the susceptibility factors present in the document. Identify the source, nature of the relationship, and target. If you don't know any answers, write the empty array [].\nDocument title: " + doc['data']['title'] + '\nAbstract: ' + doc['data']['abstract']
  #prompt = "You are a researcher who answers only in JSON arrays, no plaintext. Identify the susceptibility factors present in the document. Identify the source, nature of the relationship, and target. The only valid relationships are \"promotes\" and \"inhibits\". If you don't know any answers, write the empty array []. Example response: " + '[ { "source": "CEBPE gene promoter polymorphism (rs2239630 G > A)", "relationship": ["promotes"], "target": "B-cell acute lymphoblastic leukemia" } ]\n' + "\nDocument title: " + (doc['data']['title'] or '') + '\nAbstract: ' + (doc['data']['abstract'] or '')
  prompt = "Document title: " + (doc['data']['title'] or '') + '\nAbstract: ' + (doc['data']['abstract'] or '')
  return completions_to_answers(query(index, llm_predictor, prompt_helper, prompt + json.dumps(doc, separators=(',', ':'))), label)

def get_answer(doc, label, predictions, reviewer):
    data = {
      'answer': predictions,
      'document': doc['hash'],
      'label': label['hash'],
      'reviewer': reviewer,
      'timestamp': math.floor(time.time())
    }
    return {
      'data': data,
      'type':'label-answer'
    }

async def main():
    limit = limit = 1024 * 1024 * 10 # Allow lines up to 10 MiB

    ihost,iport = os.environ["SR_INPUT"].split(":")
    sr_input, _ = await asyncio.open_connection(ihost, iport, limit=limit)

    ohost,oport = os.environ["SR_OUTPUT"].split(":")
    _, sr_output = await asyncio.open_connection(ohost, oport, limit=limit)

    config = json.load(open(os.environ['SR_CONFIG']))
    label = config['current-labels'][0]
    reviewer = config['reviewer']

    #llm_predictor = LLMPredictor(llm=OpenAIChat(temperature=0, model_name="gpt-3.5-turbo", max_tokens=512))
    llm_predictor = ChatGPTLLMPredictor()
    index = GPTSimpleVectorIndex([], llm_predictor=llm_predictor)

    num_output = 512
    max_input_size = 4097
    max_chunk_overlap = 20
    chunk_size_limit = max_input_size - num_output
    prompt_helper = PromptHelper(max_input_size, num_output, max_chunk_overlap, chunk_size_limit=chunk_size_limit)

    doc = None
    answers = []
    while True:
      line = await sr_input.readline()
      if not line:
        await sr_output.drain()
        break

      sr_output.write(line)

      event = json.loads(line.decode().rstrip())

      if event['type'] == 'document':
        if doc:
          if len(answers):
            None
            # documents as context has not been useful
            #index_doc(index, doc, answers)
          else:
            predictions = predict_doc(index, llm_predictor, prompt_helper, doc, label)
            answer = json.dumps(get_answer(doc, label, predictions, reviewer), separators=(',', ':'))
            sr_output.write(f"{answer}\n".encode())
        doc = event
        answers = []
      elif event['type'] == 'label-answer':
        answers.append(event)
      else:
        await sr_output.drain()
