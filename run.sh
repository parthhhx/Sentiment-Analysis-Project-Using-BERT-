TRANSFORMERS_OFFLINE=1 \
python bert_fintune.py \
--num_train_epochs 3 \
--learning_rate 3e-5 \
--eval_batch_size 16 \
--bert_model 'bert-base-uncased' \
--data_dir '/home1/mamtaprj/codes/absa/english_absa/aspect_intensity/semeval_doc_intensity/data/' \
--output_dir 'logs/' \
--task_name 'senti' \
--N 12 \
--train_batch_size 16 \
--max_seq_length 80 \
--do_eval \
--do_train
