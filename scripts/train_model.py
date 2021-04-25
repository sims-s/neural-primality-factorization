from argparse import ArgumentParser
import yaml
import os
import torch
from torch.utils.data import DataLoader
import torch.optim as optim
from transformers import get_linear_schedule_with_warmup

import sys
sys.path.append('./src/')
from utils import save_json, load_json, get_max_input_size, get_max_decode_size
from tokenizer import Tokenizer
import data_utils
from data_utils import prepare_dataloader, GlobalFactorMapping, gfm
from models import Factorizer
from optimization_utils import run_training
from generation_utils import factor
from metrics_utils import compute_factorization_metrics
from utils import get_target_checkpoint, backfill_args



def load_data_file(args):
    if args['data']['data_loc'].endswith('.json'):
        return load_json(args['data']['data_loc'])
    else:
        return load_json(args['data']['data_loc'] + '2^%d.json'%args['data']['max_pow'])

def get_datasets(args):
    if args['verbose']:
        print('Loading data...')
    data = load_data_file(args)

    
    return prepare_dataloader(data['train'], args, **args['loader']['train']), \
           prepare_dataloader(data['test'], args, **args['loader']['test'])
    

def compute_extra_args(args, tokenizer):
    # Compute input/output sizes given how we're padding things
    args['data']['max_input_size'] = get_max_input_size(args['data']['max_pow'], args['data']['input_padding'])
    args['data']['max_decode_size'] = get_max_decode_size(args['data']['max_pow'])
    # Return things related to the tokenizer
    args['tokenizer'] = {}
    args['tokenizer']['n_tokens'] = len(tokenizer)
    args['tokenizer']['pad_token_id'] = tokenizer('_')[0]
    return args


def get_model(args, device):
    model = Factorizer(n_tokens = args['tokenizer']['n_tokens'], 
                        pad_token_id = args['tokenizer']['pad_token_id'],
                        max_decode_size = args['data']['max_decode_size'],
                         **args['model_args'])
    model.to(device)
    return model

def get_optimizer(args, model):
    if args['optimizer']['type'].lower()=='adam':
        opt = optim.Adam(model.parameters(), **args['optimizer']['opt_args'])
    else:
        raise ValueError('Only using adam right now')
    return opt

def get_scheduler(args, optimizer):
    # linear_schedule_with_warmup
    if args['scheduler']['type']=='linear_schedule_with_warmup':
        scheduler = get_linear_schedule_with_warmup(optimizer, args['scheduler']['n_warmup_steps'], args['scheduler']['nb_steps'])
    else:
        raise ValueError('only using linear_schedule_with_warmup right now')
    return scheduler


def get_model_opt_scheduler(args, device):
    model = get_model(args, device)
    optimizer = get_optimizer(args, model)
    scheduler = get_scheduler(args, optimizer)
    if args['verbose']:
        print('Successfully created model, optimizer, and scheduler')
        
    return model, optimizer, scheduler, args

def get_just_test_data(args):
    return load_data_file(args)['test']



def main(args):
    args = backfill_args(args)
    device = torch.device('cuda')
    tokenizer = Tokenizer()
    args = compute_extra_args(args, tokenizer)
    data_utils.gfm = GlobalFactorMapping(data_path = args['data']['data_loc'] if args['data']['data_loc'].endswith('.json') else \
                                          args['data']['data_loc'] + '2^%d.json'%args['data']['max_pow'])



    train_loader, test_loader = get_datasets(args)
    args['scheduler']['nb_steps'] = args['scheduler']['nb_epochs'] * len(train_loader)
    os.makedirs(args['io']['save_path'], exist_ok=True)
    os.makedirs(args['io']['save_path'] + 'checkpoints/', exist_ok=True)
    model, optimizer, scheduler, args = get_model_opt_scheduler(args, device)
    if args['verbose']:
        print('Running training for %d steps, %d warmup'%(args['scheduler']['nb_steps'], args['scheduler']['n_warmup_steps']))
    run_training(model, optimizer, scheduler, tokenizer, train_loader, test_loader, device, args)
    best_checkpoint = get_target_checkpoint(args['io']['save_path'])['model_state_dict']
    model.load_state_dict(best_checkpoint)
    compute_factorization_metrics(model, tokenizer, device, args)


    ## FEATURES
    
    # Training rework:
        # Ability to resume training
        # Checkpoint at not end of epoch
        # Gradient Accumulation
        # MAKE IT SO WHEN DATA IS PASSED INTO MODEL, IT'S ONLY PADDED AS MUCH AS IT NEEDS TO BE!!!

    # Other bases... More generally other tokenization methods (e.g. if a number is inputted as 2**123 or other expressions, know how to handle)
        # I think this might actually be helpful?
        # Rework tokenizer along with this
    
    # Are there other thingies that folks do with training transformers?
        # Learned Positional Embeddings

    # Some prediction head for whether or not a target # is prime
        # Model is predicting correct product
    # lower learning rates for bigger models... but not too low ;)





if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    with open(args.config, 'r') as f:
        args = yaml.safe_load(f)
    main(args)


