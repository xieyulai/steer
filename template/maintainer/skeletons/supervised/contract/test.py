"""台账终评实现（官方分数唯一来源）。禁止 ws.evaluate。"""
from __future__ import annotations

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from contract.prepare_data import _build_dataset, base_transform
from contract.runtime import DEFAULT_VAL_LOADER_BATCH_SIZE, LOCKED_DATASET


def get_test_loader(
    data_dir: str,
    batch_size: int = DEFAULT_VAL_LOADER_BATCH_SIZE,
    num_workers: int = 2,
) -> DataLoader:
    """官方测试集 loader（LOCKED_DATASET 的 test split,train=False）。"""
    test_set = _build_dataset(
        LOCKED_DATASET, data_dir, train=False, transform=base_transform(),
    )
    return DataLoader(
        test_set,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )


def run(learner, ws, *, shared_context: dict) -> dict[str, float]:
    cfg = shared_context.get("cfg", {})
    batch_size = int(cfg["BATCH_SIZE"])
    num_workers = int(cfg["NUM_WORKERS"])
    objective = shared_context.get("objective")
    contract = shared_context.get("contract")
    if contract is not None:
        data_dir = contract.data_dir
    else:
        data_dir = str(shared_context.get("data_dir", "./data"))
    test_loader = get_test_loader(
        data_dir,
        batch_size=batch_size,
        num_workers=num_workers,
    )

    learner.eval()
    correct = 0
    correct_top2 = 0
    total = 0
    total_loss = 0.0

    for data, target in test_loader:
        logits, target = ws.predict(learner, (data, target), shared_context=shared_context)
        if objective is not None:
            total_loss += objective(logits, target).item() * target.size(0)
        else:
            total_loss += F.cross_entropy(logits, target, reduction="sum").item()
        pred = logits.argmax(dim=1)
        correct += pred.eq(target).sum().item()
        _, top2 = logits.topk(2, dim=1)
        correct_top2 += top2.eq(target.view(-1, 1)).any(dim=1).sum().item()
        total += target.size(0)

    acc = correct / total if total > 0 else 0.0
    top2_acc = correct_top2 / total if total > 0 else 0.0
    return {
        "val_accuracy": acc,
        "val_loss": total_loss / total if total > 0 else 0.0,
        "val_top2_accuracy": top2_acc,
    }
