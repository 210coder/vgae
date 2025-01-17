import torch
import torch.nn as nn
import torch.nn.functional as F

from . import GCNConv
from utils import get_degree


def reparameterize(mu, logvar, training):
    if training:
        std = torch.exp(logvar)
        eps = torch.randn_like(std)
        return mu + std * eps
    else:
        return mu


class VGAE(nn.Module):
    def __init__(self, data, nhid=32, latent_dim=16):
        super(VGAE, self).__init__()
        self.encoder = Encoder(data, nhid, latent_dim, bias=False)
        self.decoder = Decoder()

    def reset_parameters(self):
        self.encoder.reset_parameters()

    def recon_loss(self, data, output):
        adj_recon = output['adj_recon']
        return data.norm * F.binary_cross_entropy_with_logits(adj_recon, data.adjmat, pos_weight=data.pos_weight)

    def loss_function(self, data, output):
        recon_loss = self.recon_loss(data, output)
        mu, logvar = output['mu'], output['logvar']
        kl = - 1 / (2 * data.num_nodes) * torch.mean(torch.sum(
            1 + 2 * logvar - mu.pow(2) - logvar.exp().pow(2), 1))
        return recon_loss + kl

    def forward(self, data):
        mu, logvar = self.encoder(data)
        z = reparameterize(mu, logvar, self.training)
        adj_recon = self.decoder(z)
        return {'adj_recon': adj_recon, 'z': z, 'mu': mu, 'logvar': logvar}


class VGAEGRA(VGAE):
    def __init__(self, data, nhid=32, latent_dim=16):
        super(VGAEGRA, self).__init__(data, nhid, latent_dim)
        alpha = 0.95
        A = data.adjmat
        D = get_degree(data.edge_list)
        Dinv = 1 / D.float()
        self.gra = alpha * torch.matmul(torch.inverse(torch.eye(data.num_nodes) - alpha * torch.matmul(A, torch.diag(Dinv))), A)
        norm = self.gra.sum()
        self.gra = self.gra / norm * (data.num_nodes ** 2)

    def recon_loss(self, data, output):
        adj_recon = output['adj_recon']
        return F.mse_loss(adj_recon, self.gra)


class Encoder(nn.Module):
    def __init__(self, data, nhid, latent_dim, bias=True):
        super(Encoder, self).__init__()
        nfeat = data.num_features
        self.gc1 = GCNConv(nfeat, nhid, bias)
        self.gc_mu = GCNConv(nhid, latent_dim, bias)
        self.gc_logvar = GCNConv(nhid, latent_dim, bias)

    def reset_parameters(self):
        self.gc1.reset_parameters()
        self.gc_mu.reset_parameters()
        self.gc_logvar.reset_parameters()

    def forward(self, data):
        x, adj = data.features, data.adj
        x = F.relu(self.gc1(x, adj))
        mu, logvar = self.gc_mu(x, adj), self.gc_logvar(x, adj)
        return mu, logvar


class Decoder(nn.Module):
    def __init__(self):
        super(Decoder, self).__init__()

    def forward(self, z):
        adj = torch.mm(z, z.t())
        return adj
