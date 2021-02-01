import torch
import torch.nn as nn

from kospeech.models.conformer import Conformer

batch_size, sequence_length, dim = 3, 12345, 80

cuda = torch.cuda.is_available()
device = torch.device('cuda' if cuda else 'cpu')


model = nn.DataParallel(Conformer(
    num_classes=10,
    input_dim=dim,
    encoder_dim=32,
    num_encoder_layers=3,
    decoder_dim=32,
    device=device,
)).to(device)

criterion = nn.CTCLoss(blank=3, zero_infinity=True)
optimizer = torch.optim.Adam(model.parameters(), lr=1e-04)

for i in range(10):
    inputs = torch.rand(batch_size, sequence_length, dim).to(device)
    input_lengths = torch.IntTensor([12345, 12300, 12000])
    targets = torch.LongTensor([[1, 3, 3, 3, 3, 3, 4, 5, 6, 2],
                                [1, 3, 3, 3, 3, 3, 4, 5, 2, 0],
                                [1, 3, 3, 3, 3, 3, 4, 2, 0, 0]]).to(device)
    target_lengths = torch.LongTensor([9, 8, 7])

    outputs, output_lengths = model(inputs, input_lengths)
    loss = criterion(outputs.transpose(0, 1), targets[:, 1:], output_lengths, target_lengths)
    loss.backward()
    optimizer.step()
    print(loss)
