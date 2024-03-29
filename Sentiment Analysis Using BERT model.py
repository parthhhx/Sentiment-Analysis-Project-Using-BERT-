"""BERT finetuning runner."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import torch.nn as nn
import torch.nn.functional as F
import csv
import torch.nn as nn
import re
import pandas as pd
import emoji
import os
import logging
import argparse
import random
from tqdm import tqdm, trange

import numpy as np
import torch
from torch.utils.data import TensorDataset, DataLoader, RandomSampler, SequentialSampler
from torch.utils.data.distributed import DistributedSampler

# from pytorch_pretrained_bert.tokenization import BertTokenizer
# from pytorch_pretrained_bert.modeling import BertModel
# from pytorch_pretrained_bert.modeling import BertForSequenceClassification
from pytorch_pretrained_bert.optimization import BertAdam

# from pytorch_pretrained_bert.file_utils import PYTORCH_PRETRAINED_BERT_CACHE
from transformers import BertTokenizer, BertModel, AdamW, BertForMaskedLM

# from transformers import BertTokenizer, BertModel
from transformers import AutoTokenizer, AutoModelWithLMHead

from transformers import get_linear_schedule_with_warmup

from pytorch_pretrained_bert.file_utils import PYTORCH_PRETRAINED_BERT_CACHE

# from transformers import *

from sklearn.metrics import accuracy_score, confusion_matrix, recall_score
from sklearn.metrics import classification_report


import os
import numpy as np

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"


logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class InputExample(object):
    """A single training/test example for simple sequence classification."""

    def __init__(self, guid, text_a, text_b=None, label=None):
        """Constructs a InputExample.
        Args:
                guid: Unique id for the example.
                text_a: string. The untokenized text of the first sequence. For single
                sequence tasks, only this sequence must be specified.
                text_b: (Optional) string. The untokenized text of the second sequence.
                Only must be specified for sequence pair tasks.
                label: (Optional) string. The label of the example. This should be
                specified for train and dev examples, but not for test examples.
        """
        self.guid = guid
        self.text_a = text_a
        self.text_b = text_b
        self.label = label


class InputFeatures(object):
    """A single set of features of data."""

    def __init__(self, input_ids, input_mask, segment_ids, label_id):
        self.input_ids = input_ids
        self.input_mask = input_mask
        self.segment_ids = segment_ids
        self.label_id = label_id


class DataProcessor(object):
    """Base class for data converters for sequence classification data sets."""

    def get_train_examples(self, data_dir):
        """Gets a collection of `InputExample`s for the train set."""
        raise NotImplementedError()

    def get_dev_examples(self, data_dir):
        """Gets a collection of `InputExample`s for the dev set."""
        raise NotImplementedError()

    def get_test_examples(self, data_dir):
        """Gets a collection of `InputExample`s for the dev set."""
        raise NotImplementedError()

    def get_labels(self):
        """Gets the list of labels for this data set."""
        raise NotImplementedError()

    # @classmethod
    # def _read_tsv(cls, input_file, quotechar=None):
    # 	"""Reads a tab separated value file."""
    # 	with open(input_file, "r", encoding='utf-8') as f:
    # 		reader = csv.reader(f, delimiter=",", quotechar=quotechar)
    # 		lines = []
    # 		for line in reader:
    # 			lines.append(line)
    # 		return lines


class SentiProcessor(DataProcessor):
    """Processor for Senti dataset."""

    def get_train_examples(self, data_dir):
        """See base class."""
        return self._create_examples(
            open(os.path.join(data_dir, "2018-Valence-reg-En-train.txt")), "train"
        )

    def get_dev_examples(self, data_dir):
        """See base class."""
        return self._create_examples(
            open(os.path.join(data_dir, "2018-Valence-reg-En-dev.txt")), "dev"
        )

    def get_test_examples(self, data_dir):
        """See base class."""
        return self._create_examples(
            open(os.path.join(data_dir, "2018-Valence-reg-En-dev.txt")), "test"
        )

    def get_labels(self):
        """See base class."""
        return ["negative", "neutral", "positive"]

    def find_with_pattern(self, pattern, s, replace=False, tag=None):
        if replace and tag == None:
            raise Exception(
                "Parameter error",
                "If replace=True you should add the tag by which the pattern will be replaced",
            )
        regex = re.compile(pattern)
        if replace:
            return re.sub(pattern, tag, " " + s + " ")
        return re.findall(pattern, " " + s + " ")

    def twitter_tokenizer(self, line):
        """Preprocess the tweet texts"""
        line = str(line)
        line = line.lower()
        line = re.sub("\s{2,}", " ", line).lower()
        line = line.replace("(", "")
        line = line.replace(")", "")
        line = re.sub(r"http\S+", "url", line)
        line = re.sub("@[\w_]+", "", line)
        line = re.sub("\|LBR\|", "", line)
        line = re.sub("\.+", "", line)
        line = re.sub("!!+", "", line)
        line = re.sub("\?+", "", line)
        line = re.sub("…", "", line)
        line = re.sub("_", "", line)
        line = re.sub("\*+", "", line)  # ****
        line = re.sub("||", "", line)
        line = line.split(" ")
        line = " ".join(line)
        line = str(line)
        # return line

        return line

    def _create_examples(self, lines, set_type):
        """Creates examples for the training and dev sets."""
        print("create examples")
        examples = []
        check_lbl = []
        cn = 0
        for line in lines:
            # print("lineeee",line.split("\t"))
            # if(cn==0):
            # 	continue
            aa = line.split("\t")
            if aa[1] == "Tweet":
                continue
            # print("yygygygygy",aa[1])
            guid = "%s-%s" % (set_type, cn)
            sent = self.twitter_tokenizer(aa[1].lower())
            score = float(aa[3])
            # print("score", sent, score)
            examples.append(
                InputExample(guid=guid, text_a=sent, text_b=None, label=score)
            )
            cn = cn + 1
        return examples


def convert_examples_to_features(examples, label_list, max_seq_length, tokenizer):
    """Loads a data file into a list of `InputBatch`s."""

    label_map = {label: i for i, label in enumerate(label_list)}

    features = []
    for ex_index, example in enumerate(examples):
        tokens_a = tokenizer.tokenize(example.text_a)
        # print("tokensssss",tokens_a)
        tokens_b = None
        if example.text_b:
            tokens_b = tokenizer.tokenize(example.text_b)
            # Modifies `tokens_a` and `tokens_b` in place so that the total
            # length is less than the specified length.
            # Account for [CLS], [SEP], [SEP] with "- 3"
            _truncate_seq_pair(tokens_a, tokens_b, max_seq_length - 3)
        else:
            # Account for [CLS] and [SEP] with "- 2"
            if len(tokens_a) > max_seq_length - 2:
                tokens_a = tokens_a[: (max_seq_length - 2)]

        # The convention in BERT is:
        # (a) For sequence pairs:
        #  tokens:   [CLS] is this jack ##son ##ville ? [SEP] no it is not . [SEP]
        #  type_ids: 0   0  0	0	0	 0	   0 0	1  1  1  1   1 1
        # (b) For single sequences:
        #  tokens:   [CLS] the dog is hairy . [SEP]
        #  type_ids: 0   0   0   0  0	 0 0
        #
        # Where "type_ids" are used to indicate whether this is the first
        # sequence or the second sequence. The embedding vectors for `type=0` and
        # `type=1` were learned during pre-training and are added to the wordpiece
        # embedding vector (and position vector). This is not *strictly* necessary
        # since the [SEP] token unambigiously separates the sequences, but it makes
        # it easier for the model to learn the concept of sequences.
        #
        # For classification tasks, the first vector (corresponding to [CLS]) is
        # used as as the "sentence vector". Note that this only makes sense because
        # the entire model is fine-tuned.
        tokens = ["[CLS]"] + tokens_a + ["[SEP]"]
        segment_ids = [0] * len(tokens)

        if tokens_b:
            tokens += tokens_b + ["[SEP]"]
            segment_ids += [1] * (len(tokens_b) + 1)

        input_ids = tokenizer.convert_tokens_to_ids(tokens)

        # The mask has 1 for real tokens and 0 for padding tokens. Only real
        # tokens are attended to.
        input_mask = [1] * len(input_ids)

        # Zero-pad up to the sequence length.
        padding = [0] * (max_seq_length - len(input_ids))
        input_ids += padding
        input_mask += padding
        segment_ids += padding

        assert len(input_ids) == max_seq_length
        assert len(input_mask) == max_seq_length
        assert len(segment_ids) == max_seq_length

        label_id = example.label
        if ex_index < 5:
            logger.info("*** Example ***")
            logger.info("guid: %s" % (example.guid))
            logger.info("tokens: %s" % " ".join([str(x) for x in tokens]))
            logger.info("input_ids: %s" % " ".join([str(x) for x in input_ids]))
            logger.info("input_mask: %s" % " ".join([str(x) for x in input_mask]))
            logger.info("segment_ids: %s" % " ".join([str(x) for x in segment_ids]))
            # logger.info("label: %d (id = %d)" % (example.label, label_id))

        features.append(
            InputFeatures(
                input_ids=input_ids,
                input_mask=input_mask,
                segment_ids=segment_ids,
                label_id=label_id,
            )
        )
    return features


def _truncate_seq_pair(tokens_a, tokens_b, max_length):
    """Truncates a sequence pair in place to the maximum length."""

    # This is a simple heuristic which will always truncate the longer sequence
    # one token at a time. This makes more sense than truncating an equal percent
    # of tokens from each, since if one sequence is very short then each token
    # that's truncated likely contains more information than a longer sequence.
    while True:
        total_length = len(tokens_a) + len(tokens_b)
        if total_length <= max_length:
            break
        if len(tokens_a) > len(tokens_b):
            tokens_a.pop()
        else:
            tokens_b.pop()


def accuracy(out, labels):
    outputs = np.argmax(out, axis=1)
    return np.sum(outputs == labels)


def warmup_linear(x, warmup=0.002):
    if x < warmup:
        return x / warmup
    return 1.0 - x


class CustomBERTModel(nn.Module):
    def __init__(self):
        super(CustomBERTModel, self).__init__()
        # config = BertConfig(output_hidden_states=True)
        # self.bert = BertForSequenceClassification.from_pretrained(args.bert_model,cache_dir=PYTORCH_PRETRAINED_BERT_CACHE / 'distributed_{}'.format(args.local_rank),num_hidden_layers=num_hidden_layers)
        self.bert = BertModel.from_pretrained(args.bert_model)

        # self.linear1 = nn.Linear(768, 256)
        self.linear2 = nn.Linear(768, 1)  ## 3 is the number of classes in this example

    def forward(self, input_ids, l, targets, seg):
        sequence_output = self.bert(
            input_ids, attention_mask=l, token_type_ids=seg
        )  # tensor=sequence_output[0]=torch.Size([16, 80, 768]), batch,len,dim

        ## extract the 1st token's embeddings to get sentence rep (cls)
        linear1_output = sequence_output[0][:, 0, :].view(
            -1, 768
        )  ## extract the 1st token's embeddings

        linear2_output = self.linear2(linear1_output)

        return linear2_output


def train(model, train_dataloader, args):
    model.train()
    global_step = 0
    tr_loss = 0
    nb_tr_examples, nb_tr_steps = 0, 0
    for step, batch in enumerate(tqdm(train_dataloader, desc="Iteration")):
        # print("step outside if...", step)
        batch = tuple(t.to(device) for t in batch)
        input_ids, input_mask, segment_ids, label_ids = batch

        outputs = model(input_ids, input_mask, label_ids, segment_ids)

        criterion = (
            nn.MSELoss()
        )  # nn.CrossEntropyLoss() ## If required define your own criterion
        loss = criterion(outputs, label_ids)

        if n_gpu > 1:
            loss = loss.mean()  # mean() to average on multi-gpu.
        if args.gradient_accumulation_steps > 1:
            loss = loss / args.gradient_accumulation_steps

        if args.fp16:
            optimizer.backward(loss)
        else:
            loss.backward()

        tr_loss += loss.item()
        nb_tr_examples += input_ids.size(0)
        nb_tr_steps += 1
        if (step + 1) % args.gradient_accumulation_steps == 0:
            # print("step.............",step)
            # modify learning rate with special warm up BERT uses
            lr_this_step = args.learning_rate * warmup_linear(
                global_step / t_total, args.warmup_proportion
            )
            for param_group in optimizer.param_groups:
                param_group["lr"] = lr_this_step
            optimizer.step()
            optimizer.zero_grad()
            global_step += 1
    epoch_loss = float(tr_loss / nb_tr_steps)
    # print(f'Epoch {z} loss --- {float(tr_loss/nb_tr_steps)}')
    return model, epoch_loss


def evaluate(model, eval_dataloader):
    model.eval()
    eval_loss, eval_accuracy = 0, 0
    nb_eval_steps, nb_eval_examples = 0, 0
    true_labels = []
    predicted_labels = []
    for input_ids, input_mask, segment_ids, label_ids in tqdm(
        eval_dataloader, desc="Evaluating"
    ):
        input_ids = input_ids.to(device)
        input_mask = input_mask.to(device)
        segment_ids = segment_ids.to(device)
        label_ids = label_ids.to(device)

        with torch.no_grad():
            eval_outputs = model(input_ids, input_mask, label_ids, segment_ids)
            # output=F.log_softmax(eval_outputs, dim=1)

            criterion = nn.MSELoss()  ## If required define your own criterion
            loss = criterion(eval_outputs, label_ids)

            # logits = model(input_ids, segment_ids, input_mask)
            logits = eval_outputs
            tmp_eval_loss = loss

        predicted_labels = (
            predicted_labels + logits.tolist()
        )  # torch.argmax(logits, dim=-1).tolist()
        true_labels = true_labels + label_ids.tolist()

        logits = logits.detach().cpu().numpy()
        label_ids = label_ids.to("cpu").numpy()

        eval_loss += tmp_eval_loss.mean().item()

        nb_eval_examples += input_ids.size(0)
        nb_eval_steps += 1

    eval_loss = eval_loss / nb_eval_steps

    return eval_loss, eval_accuracy, predicted_labels, true_labels


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    ## Required parameters
    parser.add_argument(
        "--data_dir",
        default=None,
        type=str,
        required=True,
        help="The input data dir. Should contain the .tsv files (or other data files) for the task.",
    )
    parser.add_argument(
        "--bert_model",
        default=None,
        type=str,
        required=True,
        help="Bert pre-trained model selected in the list: bert-base-uncased, "
        "bert-large-uncased, bert-base-cased, bert-large-cased, bert-base-multilingual-uncased, "
        "bert-base-multilingual-cased, bert-base-chinese.",
    )
    parser.add_argument(
        "--task_name",
        default=None,
        type=str,
        required=True,
        help="The name of the task to train.",
    )
    parser.add_argument(
        "--output_dir",
        default=None,
        type=str,
        required=True,
        help="The output directory where the model predictions and checkpoints will be written.",
    )

    ## Other parameters
    parser.add_argument(
        "--max_seq_length",
        default=128,
        type=int,
        help="The maximum total input sequence length after WordPiece tokenization. \n"
        "Sequences longer than this will be truncated, and sequences shorter \n"
        "than this will be padded.",
    )
    parser.add_argument(
        "--N", default=12, type=int, help="The number of stacked encoders. \n"
    )
    parser.add_argument(
        "--do_train", action="store_true", help="Whether to run training."
    )
    parser.add_argument(
        "--do_eval", action="store_true", help="Whether to run eval on the dev set."
    )
    parser.add_argument(
        "--do_lower_case",
        action="store_true",
        help="Set this flag if you are using an uncased model.",
    )
    parser.add_argument(
        "--train_batch_size",
        default=32,
        type=int,
        help="Total batch size for training.",
    )
    parser.add_argument(
        "--eval_batch_size", default=8, type=int, help="Total batch size for eval."
    )
    parser.add_argument(
        "--learning_rate",
        default=5e-5,
        type=float,
        help="The initial learning rate for Adam.",
    )
    parser.add_argument(
        "--num_train_epochs",
        default=3.0,
        type=float,
        help="Total number of training epochs to perform.",
    )
    parser.add_argument(
        "--warmup_proportion",
        default=0.1,
        type=float,
        help="Proportion of training to perform linear learning rate warmup for. "
        "E.g., 0.1 = 10%% of training.",
    )
    parser.add_argument(
        "--no_cuda", action="store_true", help="Whether not to use CUDA when available"
    )
    parser.add_argument(
        "--local_rank",
        type=int,
        default=-1,
        help="local_rank for distributed training on gpus",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="random seed for initialization"
    )
    parser.add_argument(
        "--gradient_accumulation_steps",
        type=int,
        default=1,
        help="Number of updates steps to accumulate before performing a backward/update pass.",
    )
    parser.add_argument(
        "--fp16",
        action="store_true",
        help="Whether to use 16-bit float precision instead of 32-bit",
    )
    parser.add_argument(
        "--loss_scale",
        type=float,
        default=0,
        help="Loss scaling to improve fp16 numeric stability. Only used when fp16 set to True.\n"
        "0 (default value): dynamic loss scaling.\n"
        "Positive power of 2: static loss scaling value.\n",
    )

    args = parser.parse_args()

    processors = {
        "senti": SentiProcessor,
    }

    num_labels_task = {
        "senti": 3,
    }

    if args.local_rank == -1 or args.no_cuda:
        device = torch.device(
            "cuda" if torch.cuda.is_available() and not args.no_cuda else "cpu"
        )
        n_gpu = torch.cuda.device_count()
    else:
        torch.cuda.set_device(args.local_rank)
        device = torch.device("cuda", args.local_rank)
        n_gpu = 1
        # Initializes the distributed backend which will take care of sychronizing nodes/GPUs
        torch.distributed.init_process_group(backend="nccl")
    logger.info(
        "device: {} n_gpu: {}, distributed training: {}, 16-bits training: {}".format(
            device, n_gpu, bool(args.local_rank != -1), args.fp16
        )
    )

    if args.gradient_accumulation_steps < 1:
        raise ValueError(
            "Invalid gradient_accumulation_steps parameter: {}, should be >= 1".format(
                args.gradient_accumulation_steps
            )
        )

    args.train_batch_size = int(
        args.train_batch_size / args.gradient_accumulation_steps
    )

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if n_gpu > 0:
        torch.cuda.manual_seed_all(args.seed)

    if not args.do_train and not args.do_eval:
        raise ValueError("At least one of `do_train` or `do_eval` must be True.")

    task_name = args.task_name.lower()

    if task_name not in processors:
        raise ValueError("Task not found: %s" % (task_name))

    processor = processors[task_name]()
    num_labels = num_labels_task[task_name]
    label_list = processor.get_labels()

    tokenizer = BertTokenizer.from_pretrained(
        args.bert_model, do_lower_case=args.do_lower_case
    )

    train_examples = None
    num_train_steps = None
    if args.do_train:
        train_examples = processor.get_train_examples(args.data_dir)
        num_train_steps = int(
            len(train_examples)
            / args.train_batch_size
            / args.gradient_accumulation_steps
            * args.num_train_epochs
        )
    print("length of train examples", len(train_examples))

    # Prepare model
    num_hidden_layers = args.N

    model = CustomBERTModel()
    model.to(torch.device("cuda"))  ##

    if args.fp16:
        model.half()
    model.to(device)
    if args.local_rank != -1:
        try:
            from apex.parallel import DistributedDataParallel as DDP
        except ImportError:
            raise ImportError(
                "Please install apex from https://www.github.com/nvidia/apex to use distributed and fp16 training."
            )

        model = DDP(model)
    elif n_gpu > 1:
        model = torch.nn.DataParallel(model)

    # Prepare optimizer
    param_optimizer = list(model.named_parameters())
    no_decay = ["bias", "LayerNorm.bias", "LayerNorm.weight"]
    optimizer_grouped_parameters = [
        {
            "params": [
                p for n, p in param_optimizer if not any(nd in n for nd in no_decay)
            ],
            "weight_decay": 0.01,
        },
        {
            "params": [
                p for n, p in param_optimizer if any(nd in n for nd in no_decay)
            ],
            "weight_decay": 0.0,
        },
    ]
    t_total = num_train_steps
    if args.local_rank != -1:
        t_total = t_total // torch.distributed.get_world_size()
    if args.fp16:
        try:
            from apex.optimizers import FP16_Optimizer
            from apex.optimizers import FusedAdam
        except ImportError:
            raise ImportError(
                "Please install apex from https://www.github.com/nvidia/apex to use distributed and fp16 training."
            )

        optimizer = FusedAdam(
            optimizer_grouped_parameters,
            lr=args.learning_rate,
            bias_correction=False,
            max_grad_norm=1.0,
        )
        if args.loss_scale == 0:
            optimizer = FP16_Optimizer(optimizer, dynamic_loss_scale=True)
        else:
            optimizer = FP16_Optimizer(optimizer, static_loss_scale=args.loss_scale)

    else:
        optimizer = BertAdam(
            optimizer_grouped_parameters,
            lr=args.learning_rate,
            warmup=args.warmup_proportion,
            t_total=t_total,
        )

    global_step = 0
    nb_tr_steps = 0
    tr_loss = 0
    if args.do_train:
        # Loading training data
        train_features = convert_examples_to_features(
            train_examples, label_list, args.max_seq_length, tokenizer
        )
        logger.info("***** Running training *****")
        logger.info("  Num examples = %d", len(train_examples))
        logger.info("  Batch size = %d", args.train_batch_size)
        logger.info("  Num steps = %d", num_train_steps)
        all_input_ids = torch.tensor(
            [f.input_ids for f in train_features], dtype=torch.long
        )
        all_input_mask = torch.tensor(
            [f.input_mask for f in train_features], dtype=torch.long
        )
        all_segment_ids = torch.tensor(
            [f.segment_ids for f in train_features], dtype=torch.long
        )
        aaa = [f.label_id for f in train_features]
        # print("aaa",aaa, type(aaa[0]))
        all_label_ids = torch.tensor(
            [f.label_id for f in train_features], dtype=torch.float
        )
        train_data = TensorDataset(
            all_input_ids, all_input_mask, all_segment_ids, all_label_ids
        )
        if args.local_rank == -1:
            train_sampler = RandomSampler(train_data)
        else:
            train_sampler = DistributedSampler(train_data)
        train_dataloader = DataLoader(
            train_data, sampler=train_sampler, batch_size=args.train_batch_size
        )

        # Loading evaluation data
        eval_examples = processor.get_dev_examples(args.data_dir)
        print("eval examples", len(eval_examples))
        eval_features = convert_examples_to_features(
            eval_examples, label_list, args.max_seq_length, tokenizer
        )
        logger.info("***** Running evaluation *****")
        logger.info("  Num examples = %d", len(eval_examples))
        logger.info("  Batch size = %d", args.eval_batch_size)

        all_input_ids = torch.tensor(
            [f.input_ids for f in eval_features], dtype=torch.long
        )
        all_input_mask = torch.tensor(
            [f.input_mask for f in eval_features], dtype=torch.long
        )
        all_segment_ids = torch.tensor(
            [f.segment_ids for f in eval_features], dtype=torch.long
        )
        all_label_ids = torch.tensor(
            [f.label_id for f in eval_features], dtype=torch.float
        )
        eval_data = TensorDataset(
            all_input_ids, all_input_mask, all_segment_ids, all_label_ids
        )

        # Run prediction for full data
        eval_sampler = SequentialSampler(eval_data)
        eval_dataloader = DataLoader(
            eval_data, sampler=eval_sampler, batch_size=args.eval_batch_size
        )

        eval_loss_ = 1e5
        # eval_accuracy_ = 0
        model_to_save = (
            model.module if hasattr(model, "module") else model
        )  # Only save the model it-self
        output_model_file = os.path.join(args.output_dir, "pytorch_model.bin")

        for z in trange(int(args.num_train_epochs), desc="Epoch"):
            model, train_loss = train(model, train_dataloader, args)
            eval_loss, eval_accuracy, _, _ = evaluate(model, eval_dataloader)
            print(
                f"|Training loss: {train_loss} |Evaluation loss: {eval_loss} Evaluation Accuracy {eval_accuracy}|"
            )
            if eval_loss < eval_loss_:
                eval_loss_ = eval_loss
                torch.save(
                    model_to_save.state_dict(), output_model_file
                )  # Save model on evaluation accuracy

        test_examples = processor.get_test_examples(args.data_dir)
        print("length of test examples", len(test_examples))
        test_features = convert_examples_to_features(
            test_examples, label_list, args.max_seq_length, tokenizer
        )
        logger.info("***** Running evaluation *****")
        logger.info("  Num examples = %d", len(test_examples))
        logger.info("  Batch size = %d", args.eval_batch_size)
        all_test_input_ids = torch.tensor(
            [f.input_ids for f in test_features], dtype=torch.long
        )
        all_test_input_mask = torch.tensor(
            [f.input_mask for f in test_features], dtype=torch.long
        )
        all_test_segment_ids = torch.tensor(
            [f.segment_ids for f in test_features], dtype=torch.long
        )
        all_test_label_ids = torch.tensor(
            [f.label_id for f in test_features], dtype=torch.float
        )
        test_data = TensorDataset(
            all_test_input_ids,
            all_test_input_mask,
            all_test_segment_ids,
            all_test_label_ids,
        )
        test_sampler = SequentialSampler(test_data)
        test_dataloader = DataLoader(
            test_data, sampler=test_sampler, batch_size=args.eval_batch_size
        )

        # new
        # Load a trained model that you have fine-tuned
        model_state_dict = torch.load(output_model_file)
        model = CustomBERTModel()
        model.load_state_dict(model_state_dict)

        model.to(device)

        label_names = ["negative", "neutral", "positive"]
        label_dict = {i: x for i, x in enumerate(label_names)}
        eval_loss, eval_accuracy, predicted_labels, true_labels = evaluate(
            model, test_dataloader
        )
        df = pd.DataFrame(columns=["text", "actual_label", "predicted_labels"])
        df["text"] = [i.text_a for i in test_examples]
        df["aspect"] = [i.text_b for i in test_examples]
        df["actual_label"] = [i for i in true_labels]
        df["predicted_labels"] = [i for i in predicted_labels]
        result = {"eval_loss": eval_loss}
        print(result)

        output_eval_file = os.path.join(args.output_dir, "eval_results.txt")
        with open(output_eval_file, "a") as writer:
            logger.info("***** Eval results *****")
            for key in sorted(result.keys()):
                logger.info("  %s = %s", key, str(result[key]))
                writer.write("%s = %s\n" % (key, str(result[key])))
        df.to_csv(os.path.join(args.output_dir, "hypothesis.csv"), sep=",")
        os.system(
            f'cat run_multi_res3.sh>{os.path.join(args.output_dir, "experiment_setting.txt")}'
        )

        from sklearn.metrics import f1_score, precision_score, recall_score

        print(len(test_examples), len(train_examples))
