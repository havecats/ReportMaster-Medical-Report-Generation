import time
import pickle
import argparse
from tqdm import tqdm
from PIL import Image
import cv2

import torch
import torchvision.transforms as transforms
from torch.utils.data import DataLoader
from torch.autograd import Variable

from utils.models import *
from utils.dataset import *
from utils.loss import *
from utils.build_tag import *

class CustomUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if name == 'Vocabulary':
            from utils.build_vocab import Vocabulary
            return Vocabulary
        return super().find_class(module, name)

class CaptionSampler(object):
    def __init__(self, args):
        self.args = args

        self.vocab = self.__init_vocab()
        self.tagger = self.__init_tagger()
        self.transform = self.__init_transform()
        self.data_loader = self.__init_data_loader(self.args.file_lits)
        self.model_state_dict = self.__load_mode_state_dict()

        self.extractor = self.__init_visual_extractor()
        self.mlc = self.__init_mlc()
        self.co_attention = self.__init_co_attention()
        self.sentence_model = self.__init_sentence_model()
        self.word_model = self.__init_word_word()

        self.ce_criterion = self._init_ce_criterion()
        self.mse_criterion = self._init_mse_criterion()

    @staticmethod
    def _init_ce_criterion():
        return nn.CrossEntropyLoss(size_average=False, reduce=False)

    @staticmethod
    def _init_mse_criterion():
        return nn.MSELoss()

    # def test(self):
    #     tag_loss, stop_loss, word_loss, loss = 0, 0, 0, 0
    #     # self.extractor.eval()
    #     # self.mlc.eval()
    #     # self.co_attention.eval()
    #     # self.sentence_model.eval()
    #     # self.word_model.eval()
    #
    #     for i, (images, _, label, captions, prob) in enumerate(self.data_loader):
    #         batch_tag_loss, batch_stop_loss, batch_word_loss, batch_loss = 0, 0, 0, 0
    #         images = self.__to_var(images, requires_grad=False)
    #
    #         visual_features, avg_features = self.extractor.forward(images)
    #         tags, semantic_features = self.mlc.forward(avg_features)
    #
    #         batch_tag_loss = self.mse_criterion(tags, self.__to_var(label, requires_grad=False)).sum()
    #
    #         sentence_states = None
    #         prev_hidden_states = self.__to_var(torch.zeros(images.shape[0], 1, self.args.hidden_size))
    #
    #         context = self.__to_var(torch.Tensor(captions).long(), requires_grad=False)
    #         prob_real = self.__to_var(torch.Tensor(prob).long(), requires_grad=False)
    #
    #         for sentence_index in range(captions.shape[1]):
    #             ctx, v_att, a_att = self.co_attention.forward(avg_features,
    #                                                    semantic_features,
    #                                                    prev_hidden_states)
    #
    #             topic, p_stop, hidden_states, sentence_states = self.sentence_model.forward(ctx,
    #                                                                                         prev_hidden_states,
    #                                                                                         sentence_states)
    #
    #             batch_stop_loss += self.ce_criterion(p_stop.squeeze(), prob_real[:, sentence_index]).sum()
    #
    #             for word_index in range(1, captions.shape[2]):
    #                 words = self.word_model.forward(topic, context[:, sentence_index, :word_index])
    #                 word_mask = (context[:, sentence_index, word_index] > 0).float()
    #                 batch_word_loss += (self.ce_criterion(words, context[:, sentence_index, word_index])
    #                                     * word_mask).sum()
    #
    #         batch_loss = self.args.lambda_tag * batch_tag_loss \
    #                      + self.args.lambda_stop * batch_stop_loss \
    #                      + self.args.lambda_word * batch_word_loss
    #
    #         tag_loss += self.args.lambda_tag * batch_tag_loss.data
    #         stop_loss += self.args.lambda_stop * batch_stop_loss.data
    #         word_loss += self.args.lambda_word * batch_word_loss.data
    #         loss += batch_loss.data
    #
    #     return tag_loss, stop_loss, word_loss, loss

    def generate(self):
        self.extractor.eval()
        # self.mlc.eval()
        # self.co_attention.eval()
        # self.sentence_model.eval()
        # self.word_model.eval()

        progress_bar = tqdm(self.data_loader, desc='Generating  /batch ')
        results = {}

        for images, image_id, label, captions, _ in progress_bar:
            images = self.__to_var(images, requires_grad=False)
            visual_features, avg_features = self.extractor.forward(images)
            tags, semantic_features = self.mlc.forward(avg_features)

            sentence_states = None
            prev_hidden_states = self.__to_var(torch.zeros(images.shape[0], 1, self.args.hidden_size))
            pred_sentences = {}
            real_sentences = {}
            for i in image_id:
                pred_sentences[i] = {}
                real_sentences[i] = {}

            for i in range(self.args.s_max):
                ctx, alpha_v, alpha_a = self.co_attention.forward(avg_features, semantic_features, prev_hidden_states)

                # # /////////
                # cam = torch.mul(visual_features, alpha_v.view(alpha_v.shape[0], alpha_v.shape[1], 1, 1)).sum(1)
                # cam.squeeze_()
                # cam = cam.cpu().data.numpy()
                # for i in range(cam.shape[0]):
                #     heatmap = cam[i]
                #     heatmap = heatmap / np.max(heatmap)
                #     print(heatmap.shape)
                # # ///////////

                topic, p_stop, hidden_state, sentence_states = self.sentence_model.forward(ctx,
                                                                                          prev_hidden_states,
                                                                                          sentence_states)
                p_stop = p_stop.squeeze(1)
                p_stop = torch.max(p_stop, 1)[1].unsqueeze(1)

                start_tokens = np.zeros((topic.shape[0], 1))
                start_tokens[:, 0] = self.vocab('<start>')
                start_tokens = self.__to_var(torch.Tensor(start_tokens).long(), requires_grad=False)

                sampled_ids = self.word_model.sample(topic, start_tokens)
                prev_hidden_states = hidden_state
                sampled_ids = torch.from_numpy(sampled_ids) * p_stop.cpu() # unsupported operand type(s) for *: 'numpy.ndarray' and 'Tensor'，使用torch.from_numpy

                if self.args.visual_model_name == 'clip':
                    self._generate_cam_clip(image_id,  i)
                else:
                    self._generate_cam(image_id, visual_features, alpha_v, i)

                for id, array in zip(image_id, sampled_ids):
                    pred_sentences[id][i] = self.__vec2sent(array.cpu().detach().numpy())

            for id, array in zip(image_id, captions):
                for i, sent in enumerate(array):
                    real_sentences[id][i] = self.__vec2sent(sent)

            for id, pred_tag, real_tag in zip(image_id, tags, label):
                results[id] = {
                    # 'Real Tags': self.tagger.inv_tags2array(real_tag),
                    'Pred Tags': self.tagger.array2tags(torch.topk(pred_tag, self.args.k)[1].cpu().detach().numpy()),
                    'Pred Sent': pred_sentences[id],
                    'Real Sent': real_sentences[id]
                }

        self.__save_json(results)
        # print(results)
        return results

    def _generate_cam_clip(self, images_id, sentence_id):
        # progress_bar = tqdm(self.data_loader, desc='Generating  /batch ')
        # results = {}
        for images, image_id, label, captions, _ in self.data_loader:
            cam_dir, cam_flag = self.__init_cam_path(images_id[0])
            if cam_flag:
                return

        densenet = VisualFeatureExtractor(model_name='densenet201',
                                       pretrained=self.args.pretrained)
        densenet_state_dict = torch.load(os.path.join(self.args.model_dir, 'densenet561.pth.tar'))
        if densenet_state_dict is not None:
            print("densenet Visual Extractor Loaded!")
            densenet.load_state_dict(densenet_state_dict['extractor'])
        if self.args.cuda:
            densenet = densenet.cuda()

        mlc = MLC(classes=self.args.classes,
                    sementic_features_dim=self.args.sementic_features_dim,
                    fc_in_features=densenet.out_features,
                    k=self.args.k)
        if densenet_state_dict is not None:
            print("densenet MLC Loaded!")
            mlc.load_state_dict(densenet_state_dict['mlc'])
        if self.args.cuda:
            mlc = mlc.cuda()

        co_attention = CoAttention(version=self.args.attention_version,
                            embed_size=self.args.embed_size,
                            hidden_size=self.args.hidden_size,
                            visual_size=densenet.out_features,
                            k=self.args.k,
                            momentum=self.args.momentum)
        if densenet_state_dict is not None:
            print("Co-Attention Loaded!")
            co_attention.load_state_dict(densenet_state_dict['co_attention'])
        if self.args.cuda:
            co_attention = co_attention.cuda()


        del densenet_state_dict

        for images, image_id, label, captions, _ in self.data_loader:
            images = self.__to_var(images, requires_grad=False)
            visual_features, avg_features = densenet.forward(images)
            tags, semantic_features = mlc.forward(avg_features)

            sentence_states = None
            prev_hidden_states = self.__to_var(torch.zeros(images.shape[0], 1, self.args.hidden_size))
            pred_sentences = {}
            real_sentences = {}
            for i in image_id:
                pred_sentences[i] = {}
                real_sentences[i] = {}
            for i in range(self.args.s_max):
                ctx, alpha_v, alpha_a = co_attention.forward(avg_features, semantic_features, prev_hidden_states)

# /////
                alpha_v *= 10000
                cam = torch.mul(visual_features, alpha_v.view(alpha_v.shape[0], alpha_v.shape[1], 1, 1)).sum(1)
                cam.squeeze_(1)
                cam = cam.cpu().data.numpy()
                for i in range(cam.shape[0]):
                    image_id = images_id[i]
                    cam_dir, cam_flag = self.__init_cam_path(images_id[i])

                    org_img = cv2.imread(os.path.join(self.args.image_dir, image_id), 1)
                    org_img = cv2.resize(org_img, (self.args.cam_size, self.args.cam_size))

                    heatmap = cam[i]
                    heatmap = heatmap / np.max(heatmap)
                    heatmap = cv2.resize(heatmap, (self.args.cam_size, self.args.cam_size))
                    heatmap = cv2.applyColorMap(np.uint8(255 * heatmap), cv2.COLORMAP_JET)

                    img = heatmap * 0.5 + org_img
                    cv2.imwrite(os.path.join(cam_dir, '{}.png'.format(sentence_id)), img)
                    break
        del densenet
        del mlc


    def _generate_cam(self, images_id, visual_features, alpha_v, sentence_id):
        alpha_v *= 10000
        cam = torch.mul(visual_features, alpha_v.view(alpha_v.shape[0], alpha_v.shape[1], 1, 1)).sum(1)
        cam.squeeze_(1)
        cam = cam.cpu().data.numpy()
        for i in range(cam.shape[0]):
            image_id = images_id[i]
            cam_dir, cam_flag = self.__init_cam_path(images_id[i])

            org_img = cv2.imread(os.path.join(self.args.image_dir, image_id), 1)
            org_img = cv2.resize(org_img, (self.args.cam_size, self.args.cam_size))

            heatmap = cam[i]
            heatmap = heatmap / np.max(heatmap)
            heatmap = cv2.resize(heatmap, (self.args.cam_size, self.args.cam_size))
            heatmap = cv2.applyColorMap(np.uint8(255 * heatmap), cv2.COLORMAP_JET)

            img = heatmap * 0.5 + org_img
            cv2.imwrite(os.path.join(cam_dir, '{}.png'.format(sentence_id)), img)
            break


    def __init_cam_path(self, image_file):
        generate_dir = os.path.join(self.args.image_dir, self.args.generate_dir)
        if not os.path.exists(generate_dir):
            os.makedirs(generate_dir)
        cam_flag = False
        image_dir = os.path.join(generate_dir, image_file)

        if not os.path.exists(image_dir):
            os.makedirs(image_dir)
        else:
            cam_flag = True
        return image_dir, cam_flag

    def __save_json(self, result):
        result_path = os.path.join(self.args.model_dir.replace('models','logs'), self.args.result_path)
        if not os.path.exists(result_path):
            os.makedirs(result_path)
        with open(os.path.join(result_path, '{}.json'.format(self.args.result_name)), 'w') as f:
            json.dump(result, f)

    def __load_mode_state_dict(self):
        try:
            model_state_dict = torch.load(os.path.join(self.args.model_dir, self.args.load_model_path))
            print("[Load Model-{} Succeed!]".format(self.args.load_model_path))
            print("Load From Epoch {}".format(model_state_dict['epoch']))
            return model_state_dict
        except Exception as err:
            print("[Load Model Failed] {}".format(err))
            raise err

    def __init_tagger(self):
        return Tag()

    def __vec2sent(self, array):
        sampled_caption = []
        for word_id in array:
            word = self.vocab.get_word_by_id(word_id)
            if word == '<start>':
                continue
            if word == '<end>' or word == '<pad>':
                break
            sampled_caption.append(word)
        return ' '.join(sampled_caption)

    def __init_vocab(self):
        # with open(self.args.vocab_path, 'rb') as f:
        #     vocab = pickle.load(f)

        vocab = CustomUnpickler(open(self.args.vocab_path, 'rb')).load()

        return vocab

    def __init_data_loader(self, file_list):
        data_loader = get_loader(image_dir=self.args.image_dir,
                                 caption_json=self.args.caption_json,
                                 file_list=file_list,
                                 vocabulary=self.vocab,
                                 transform=self.transform,
                                 batch_size=self.args.batch_size,
                                 s_max=self.args.s_max,
                                 n_max=self.args.n_max,
                                 shuffle=False,
                                 load_image_or=self.args.load_image_or)
        return data_loader

    def __init_transform(self):
        transform = transforms.Compose([
            transforms.Resize((self.args.resize, self.args.resize)),
            transforms.ToTensor(),
            transforms.Normalize((0.485, 0.456, 0.406),
                                 (0.229, 0.224, 0.225))])
        return transform

    def __to_var(self, x, requires_grad=True):
        if self.args.cuda:
            x = x.cuda()
        return Variable(x, requires_grad=requires_grad)

    def __init_visual_extractor(self):
        model = VisualFeatureExtractor(model_name=self.args.visual_model_name,
                                       pretrained=self.args.pretrained)

        if self.model_state_dict is not None:
            print("Visual Extractor Loaded!")
            model.load_state_dict(self.model_state_dict['extractor'])

        if self.args.cuda:
            model = model.cuda()

        return model

    def __init_mlc(self):
        model = MLC(classes=self.args.classes,
                    sementic_features_dim=self.args.sementic_features_dim,
                    fc_in_features=self.extractor.out_features,
                    k=self.args.k)

        if self.model_state_dict is not None:
            print("MLC Loaded!")
            model.load_state_dict(self.model_state_dict['mlc'])

        if self.args.cuda:
            model = model.cuda()

        return model

    def __init_co_attention(self):
        model = CoAttention(version=self.args.attention_version,
                            embed_size=self.args.embed_size,
                            hidden_size=self.args.hidden_size,
                            visual_size=self.extractor.out_features,
                            k=self.args.k,
                            momentum=self.args.momentum)

        if self.model_state_dict is not None:
            print("Co-Attention Loaded!")
            model.load_state_dict(self.model_state_dict['co_attention'])

        if self.args.cuda:
            model = model.cuda()

        return model

    def __init_sentence_model(self):
        model = SentenceLSTM(version=self.args.sent_version,
                             embed_size=self.args.embed_size,
                             hidden_size=self.args.hidden_size,
                             num_layers=self.args.sentence_num_layers,
                             dropout=self.args.dropout,
                             momentum=self.args.momentum)

        if self.model_state_dict is not None:
            print("Sentence Model Loaded!")
            model.load_state_dict(self.model_state_dict['sentence_model'])

        if self.args.cuda:
            model = model.cuda()

        return model

    def __init_word_word(self):
        model = WordLSTM(vocab_size=len(self.vocab),
                         embed_size=self.args.embed_size,
                         hidden_size=self.args.hidden_size,
                         num_layers=self.args.word_num_layers,
                         n_max=self.args.n_max)

        if self.model_state_dict is not None:
            print("Word Model Loaded!")
            model.load_state_dict(self.model_state_dict['word_model'])

        if self.args.cuda:
            model = model.cuda()

        return model

def test_generate(model, image_path):
    import warnings
    warnings.filterwarnings("ignore")

    parser = argparse.ArgumentParser()

    paths = []
    paths.append(image_path)
    paths.append('D:/coding/Jupyter/Medical-Report-Generation-OntheAutomaticGeneration/data/images/CXR1000_IM-0003-1001.png')
    paths.append(
        'D:/coding/Jupyter/Medical-Report-Generation-OntheAutomaticGeneration/data/images/CXR1_1_IM-0001-3001.png')
    paths.append(
        'D:/coding/Jupyter/Medical-Report-Generation-OntheAutomaticGeneration/data/images/CXR3_IM-1384-1001.png')
    # paths.append(
    #     'D:/coding/Jupyter/Medical-Report-Generation-OntheAutomaticGeneration/data/images/CXR29_IM-1302-1001.png')


    """
    Data Argument
    """
    # Path Argument
    parser.add_argument('--image_dir', type=str, default='./data/images',
                        help='the path for images')

    parser.add_argument('--model_dir', type=str, default='./models')
    parser.add_argument('--caption_json', type=str, default='./data/new_data/captions.json',
                        help='path for captions')
    parser.add_argument('--vocab_path', type=str, default='./data/new_data/vocab.pkl',
                        help='the path for vocabulary object')
    parser.add_argument('--load_model_path', type=str, default='clip480.pth.tar',
                        help='The path of loaded model')
    parser.add_argument('--file_lits', type=list,
                        default=paths,
                        help='the path for test file list')
    parser.add_argument('--load_image_or', action='store_true', default=True,
                        help='load images from paths or load from text')

    # transforms argument
    parser.add_argument('--resize', type=int, default=224,
                        help='size for resizing images')

    # CAM
    parser.add_argument('--cam_size', type=int, default=224)
    parser.add_argument('--generate_dir', type=str, default='cam')

    # Saved result
    parser.add_argument('--result_path', type=str, default='results',
                        help='the path for storing results')
    parser.add_argument('--result_name', type=str, default='test',
                        help='the name of results')

    """
    Model argument
    """
    parser.add_argument('--momentum', type=int, default=0.1)
    # VisualFeatureExtractor

    parser.add_argument('--visual_model_name', type=str, default='clip',
                        help='CNN model name')
    parser.add_argument('--pretrained', action='store_true', default=False,
                        help='not using pretrained model when training')

    # MLC
    parser.add_argument('--classes', type=int, default=210)
    parser.add_argument('--sementic_features_dim', type=int, default=512)
    parser.add_argument('--k', type=int, default=10)

    # Co-Attention
    parser.add_argument('--attention_version', type=str, default='v1')
    parser.add_argument('--embed_size', type=int, default=512)
    parser.add_argument('--hidden_size', type=int, default=512)

    # Sentence Model
    parser.add_argument('--sent_version', type=str, default='v2')
    parser.add_argument('--sentence_num_layers', type=int, default=2)
    parser.add_argument('--dropout', type=float, default=0.1)

    # Word Model
    parser.add_argument('--word_num_layers', type=int, default=1)

    """
    Generating Argument
    """
    parser.add_argument('--s_max', type=int, default=6)
    parser.add_argument('--n_max', type=int, default=30)

    parser.add_argument('--batch_size', type=int, default=4)  # 原为8，改为6

    # Loss function
    parser.add_argument('--lambda_tag', type=float, default=10000)
    parser.add_argument('--lambda_stop', type=float, default=10)
    parser.add_argument('--lambda_word', type=float, default=1)



    args = parser.parse_args()
    args.cuda = torch.cuda.is_available()

    if model == 'clip':
        args.load_model_path = 'clip480.pth.tar'
        args.visual_model_name = 'clip'
    elif model == 'densenet':
        args.load_model_path = 'densenet561.pth.tar'
        args.visual_model_name = 'densenet201'

    print(args)

    sampler = CaptionSampler(args)
    # tag_loss, stop_loss, word_loss, loss = sampler.test()
    #
    # print("tag loss:{}".format(tag_loss))
    # print("stop loss:{}".format(stop_loss))
    # print("word loss:{}".format(word_loss))
    # print("loss:{}".format(loss))
    result = sampler.generate()
    print(result)
    return result


if __name__ == '__main__':
    import warnings
    warnings.filterwarnings("ignore")

    parser = argparse.ArgumentParser()
    image_path = 'D:/coding/Jupyter/Medical-Report-Generation-OntheAutomaticGeneration/data/images/CXR219_IM-0799-1001.png'
    model = 'densenet'

    paths = []
    paths.append(image_path)
    paths.append('D:/coding/Jupyter/Medical-Report-Generation-OntheAutomaticGeneration/data/images/CXR1000_IM-0003-1001.png')
    paths.append(
        'D:/coding/Jupyter/Medical-Report-Generation-OntheAutomaticGeneration/data/images/CXR1_1_IM-0001-3001.png')
    paths.append(
        'D:/coding/Jupyter/Medical-Report-Generation-OntheAutomaticGeneration/data/images/CXR3_IM-1384-1001.png')
    # paths.append(
    #     'D:/coding/Jupyter/Medical-Report-Generation-OntheAutomaticGeneration/data/images/CXR29_IM-1302-1001.png')


    """
    Data Argument
    """
    # Path Argument
    parser.add_argument('--image_dir', type=str, default='D:/coding/Jupyter/Medical-Report-Generation-OntheAutomaticGeneration/data/images',
                        help='the path for images')

    parser.add_argument('--model_dir', type=str, default='./models')
    parser.add_argument('--caption_json', type=str, default='./data/new_data/captions.json',
                        help='path for captions')
    parser.add_argument('--vocab_path', type=str, default='./data/new_data/vocab.pkl',
                        help='the path for vocabulary object')
    parser.add_argument('--load_model_path', type=str, default='clip480.pth.tar',
                        help='The path of loaded model')
    parser.add_argument('--file_lits', type=list,
                        default=paths,
                        help='the path for test file list')
    parser.add_argument('--load_image_or', action='store_true', default=True,
                        help='load images from paths or load from text')

    # transforms argument
    parser.add_argument('--resize', type=int, default=224,
                        help='size for resizing images')

    # CAM
    parser.add_argument('--cam_size', type=int, default=224)
    parser.add_argument('--generate_dir', type=str, default='cam')

    # Saved result
    parser.add_argument('--result_path', type=str, default='results',
                        help='the path for storing results')
    parser.add_argument('--result_name', type=str, default='test11',
                        help='the name of results')

    """
    Model argument
    """
    parser.add_argument('--momentum', type=int, default=0.1)
    # VisualFeatureExtractor

    parser.add_argument('--visual_model_name', type=str, default='clip',
                        help='CNN model name')
    parser.add_argument('--pretrained', action='store_true', default=False,
                        help='not using pretrained model when training')

    # MLC
    parser.add_argument('--classes', type=int, default=210)
    parser.add_argument('--sementic_features_dim', type=int, default=512)
    parser.add_argument('--k', type=int, default=10)

    # Co-Attention
    parser.add_argument('--attention_version', type=str, default='v1')
    parser.add_argument('--embed_size', type=int, default=512)
    parser.add_argument('--hidden_size', type=int, default=512)

    # Sentence Model
    parser.add_argument('--sent_version', type=str, default='v2')
    parser.add_argument('--sentence_num_layers', type=int, default=2)
    parser.add_argument('--dropout', type=float, default=0.1)

    # Word Model
    parser.add_argument('--word_num_layers', type=int, default=1)

    """
    Generating Argument
    """
    parser.add_argument('--s_max', type=int, default=6)
    parser.add_argument('--n_max', type=int, default=30)

    parser.add_argument('--batch_size', type=int, default=4)  # 原为8，改为6

    # Loss function
    parser.add_argument('--lambda_tag', type=float, default=10000)
    parser.add_argument('--lambda_stop', type=float, default=10)
    parser.add_argument('--lambda_word', type=float, default=1)



    args = parser.parse_args()
    args.cuda = torch.cuda.is_available()

    if model == 'clip':
        args.load_model_path = 'clip480.pth.tar'
        args.visual_model_name = 'clip'
    elif model == 'densenet':
        args.load_model_path = 'densenet561.pth.tar'
        args.visual_model_name = 'densenet201'

    print(args)

    sampler = CaptionSampler(args)
    # tag_loss, stop_loss, word_loss, loss = sampler.test()
    #
    # print("tag loss:{}".format(tag_loss))
    # print("stop loss:{}".format(stop_loss))
    # print("word loss:{}".format(word_loss))
    # print("loss:{}".format(loss))

    result = sampler.generate()
    print(result)