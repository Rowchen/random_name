import torch as tr
import torch.nn as nn
import torch.nn.init as init
import torch.nn.functional as F
import torch.optim as opt
import pandas as pd
import numpy as np
import torchvision
from torch.autograd import Variable
import torch.nn.utils as utils

class TextRNN(nn.Module):
    def __init__(self,arg,sta_feat=None):
        super(TextRNN,self).__init__()
        self.N=arg.doc_length
        V=arg.embed_dim
        self.weight_decay=arg.weight_decay
        self.lr1=arg.lr1
        self.lr2=arg.lr2
        
        #embedding
        self.embed=nn.Embedding(arg.vocab_size,V,scale_grad_by_freq=True,max_norm=5)
        self.embed.weight.data.copy_(tr.from_numpy(arg.pretrained_weight))
        self.embed.weight.requires_grad = arg.finetune
        self.finetune=arg.finetune
        
        #BiLSTM
        self.num_layers=arg.num_layers
        self.hidden_size=arg.hidden_size
        self.lstm=nn.LSTM(V, 
                          arg.hidden_size, 
                          num_layers=arg.num_layers,
                          batch_first=True,
                          bidirectional = (arg.useBi==2))
        
        self.sta_feat=sta_feat
        if sta_feat is not None:
            add_dim=sta_feat.shape[1]
            sta_feat2=(sta_feat-np.mean(sta_feat,axis=0))/np.std(sta_feat,axis=0)
            self.sta_feat=tr.from_numpy(sta_feat2).float().cuda()
        else:
            add_dim=0
            
        #fc
        self.fc = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(self.hidden_size*2*2*arg.useBi+add_dim,arg.fc_hiddim),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Linear(arg.fc_hiddim,1)
        )
         #weight init
        init.xavier_normal_(self.fc[1].weight.data, gain=np.sqrt(1))
        init.xavier_normal_(self.fc[4].weight.data, gain=np.sqrt(1))
        init.xavier_normal_(self.lstm.all_weights[0][0], gain=np.sqrt(1))
        init.xavier_normal_(self.lstm.all_weights[0][1], gain=np.sqrt(1))
        
        
        
    def forward(self,x):
        '''
        input  x is [n,2,N,V]
        '''
        emb=self.embed(x[:,:,:self.N])#[num,2,N,V]  self.N is the idx of sta_feat
        x1=emb[:,0,:,:]
        x2=emb[:,1,:,:]
  
        
        o1a,_=self.lstm(x1)
        o1b,_=self.lstm(x2)
        
        o2a=o1a.permute(0,2,1)
        o2b=o1b.permute(0,2,1)#(batch,hidden,seq)
        
        o3a=F.avg_pool1d(o2a,o2a.size(2)).squeeze()
        o4a=F.max_pool1d(o2a,o2a.size(2)).squeeze()
        o5a=tr.cat([o3a,o4a],1)
        
        o3b=F.avg_pool1d(o2b,o2b.size(2)).squeeze()
        o4b=F.max_pool1d(o2b,o2b.size(2)).squeeze()
        o5b=tr.cat([o3b,o4b],1)
        
        delta1=tr.abs(o5a-o5b)     

        o6a=o5a/tr.sqrt(tr.sum(o5a**2,dim=1,keepdim=True))
        o6b=o5b/tr.sqrt(tr.sum(o5b**2,dim=1,keepdim=True))
        delta2=o6a*o6b
        
        
        idx=x[:,0,-1]
        if self.sta_feat is not None:
            out=tr.cat([delta1,delta2,self.sta_feat[idx]],1)
        else:
            out=tr.cat([delta1,delta2],1)
        
        out2=F.sigmoid(self.fc(out)).view(-1)
        
        return out2
    
    
    
    
    def get_opter(self,lr1,lr2):
        ignored_params = list(map(id, self.embed.parameters()))
        base_params = filter(lambda p: id(p) not in ignored_params,
                        self.parameters())
        if not self.finetune:
            opter=opt.Adam ([dict(params=base_params,weight_decay =self.weight_decay,lr=lr1)])
        else:
            opter=opt.Adam ([
                            dict(params=base_params,weight_decay =self.weight_decay,lr=lr1),
                            {'params': self.embed.parameters(), 'lr': lr2}
                            ]) 
        return opter

