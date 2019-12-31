import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts
import argparse

from model import SentimentClassifier
from SSTDataset import SSTDataset


def get_accuracy_from_logits(logits, labels):
    probs = torch.sigmoid(logits.unsqueeze(-1))
    soft_probs = (probs > 0.5).long()
    acc = (soft_probs.squeeze() == labels).float().mean()
    return acc


def evaluate(model, criterion, dataloader, args):
    model.eval()

    mean_acc, mean_loss = 0, 0
    count = 0

    with torch.no_grad():
        for seq, attn_masks, labels in dataloader:
            seq, attn_masks, labels = seq.cuda(args["gpu"]), attn_masks.cuda(args["gpu"]), labels.cuda(args["gpu"])
            logits = model(seq, attn_masks)
            mean_loss += criterion(logits.squeeze(-1), labels.float()).item()
            mean_acc += get_accuracy_from_logits(logits, labels)
            count += 1

    return mean_acc / count, mean_loss / count


def train(model, criterion, optimizer, scheduler, train_loader, val_loader, starting_epoch, args):
    best_acc = 0
    iters = len(train_loader)
    for epoch in range(starting_epoch, args["max_eps"]):
        model.train()

        for it, (seq, attn_masks, labels) in enumerate(train_loader):
            # Clear gradients
            scheduler.step(epoch + it / iters)
            optimizer.zero_grad()
            # Converting these to cuda tensors
            seq, attn_masks, labels = seq.cuda(args["gpu"]), attn_masks.cuda(args["gpu"]), labels.cuda(args["gpu"])

            # Obtaining the logits from the model
            logits = model(seq, attn_masks)

            # Computing loss
            loss = criterion(logits.squeeze(-1), labels.float())

            # Backpropagating the gradients
            loss.backward()

            # Optimization step
            optimizer.step()

            if it % args["print_every"] == 0:
                acc = get_accuracy_from_logits(logits, labels)
                print("Iteration {} of epoch {} complete. Loss : {} Accuracy : {}".format(it, epoch, loss.item(), acc))

        val_acc, val_loss = evaluate(model, criterion, val_loader, args)
        print("Epoch {} complete! Validation Accuracy : {}, Validation Loss : {}".format(epoch, val_acc, val_loss))
        if val_acc > best_acc:
            print("Best validation accuracy improved from {} to {}, saving model...".format(best_acc, val_acc))
            best_acc = val_acc
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "scheduler_state_dict": scheduler.state_dict(),
                "evaluation_accuracy": best_acc,
                "args": args
            }, "models/sst_finetuned_epoch=%s" % epoch)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpu', type=int, default=0)
    parser.add_argument('--freeze_bert', action='store_true')
    parser.add_argument('--maxlen', type=int, default=25)
    parser.add_argument('--batch_size', type=int, default=32)
    parser.add_argument('--lr', type=float, default=2e-5)
    parser.add_argument('--print_every', type=int, default=100)
    parser.add_argument('--max_eps', type=int, default=5)
    parser.add_argument('--dropout', type=float, default=0.5)
    parser.add_argument('--checkpoint', type=str, required=False)
    parser.add_argument('--SGDR_T0', type=int, required=False, default=4)
    parser.add_argument('--SGDR_T_MULT', type=int, required=False, default=2)
    parser.add_argument('--SGDR_ETA_MIN', type=float, required=False, default=0)

    args = parser.parse_args()
    args = args.__dict__
    print("Passed args:")
    print(args)

    checkpoint = None
    if args["checkpoint"]:
        print("Found checkpoint")
        checkpoint = torch.load(args["checkpoint"])
        old_args = checkpoint["args"]
        print("Loading args:" % old_args)

        # replace old args with any provided arg if provided
        for key in args:
            print("Substituting %s:%s with %s:%s" % (key, old_args[key], key, old_args[key]))
            old_args[key] = args[key]

        # replace args
        args = old_args

        # clean up a bit
        args.pop("checkpoint", None)

        print("New args:")
        print(args)

    # Instantiating the classifier model
    print("Building Model")
    model = SentimentClassifier(args["freeze_bert"], args["dropout"])
    model.cuda(args["gpu"])  # Enable gpu support for the model

    print("Creating criterion and optimizer objects")
    criterion = nn.BCEWithLogitsLoss()
    optimizer = optim.SGD(model.parameters(), lr=args["lr"])

    # Creating dataloaders
    print("Creating train and val dataloaders")
    dataset_train = SSTDataset(filename='data/SST-2/train.tsv', maxlen=args["maxlen"])
    dataset_validation = SSTDataset(filename='data/SST-2/dev.tsv', maxlen=args["maxlen"])

    train_loader = DataLoader(dataset_train, batch_size=args["batch_size"], num_workers=5,
                              shuffle=True, drop_last=True)
    val_loader = DataLoader(dataset_validation, batch_size=args["batch_size"], num_workers=5,
                            shuffle=True, drop_last=True)

    starting_epoch = 0
    if checkpoint:
        print("Loading state dict")
        model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        print("Starting training from evaluation accuracy: %s" % checkpoint["evaluation_accuracy"])
        starting_epoch = checkpoint["epoch"] + 1

    scheduler = CosineAnnealingWarmRestarts(optimizer, T_0=args["SGDR_T0"], T_mult=args["SGDR_T_MULT"],
                                            eta_min=args["SGDR_ETA_MIN"],
                                            last_epoch=checkpoint["epoch"] if checkpoint else -1)

    if checkpoint:
        scheduler.load_state_dict(checkpoint["scheduler_state_dict"])

    train(model, criterion, optimizer, scheduler, train_loader, val_loader, starting_epoch, args)
