import numpy as np

from nolearn.lasagne import BatchIterator

class MyBatchIterator(BatchIterator):

    def transform(self, Xb, yb):
        Xb, yb = super(MyBatchIterator, self).transform(Xb, yb)



        # # Flip half of the images in this batch at random:
        # bs = Xb.shape[0]
        # indices = np.random.choice(bs, bs / 2, replace=False)
        # Xb[indices] = Xb[indices, :, :, ::-1]

        # if yb is not None:
        #     # Horizontal flip of all x coordinates:
        #     yb[indices, ::2] = yb[indices, ::2] * -1

        #     # Swap places, e.g. left_eye_center_x -> right_eye_center_x
        #     for a, b in self.flip_indices:
        #         yb[indices, a], yb[indices, b] = (
        #             yb[indices, b], yb[indices, a])

        return Xb, yb

class EarlyStopping(object):
    def __init__(self, patience=100):
        self.patience = patience
        self.best_valid = np.inf
        self.best_valid_epoch = 0
        self.best_weights = None

    def __call__(self, nn, train_history):
        current_valid = train_history[-1]['valid_loss']
        current_epoch = train_history[-1]['epoch']
        if current_valid < self.best_valid:
            self.best_valid = current_valid
            self.best_valid_epoch = current_epoch
            self.best_weights = nn.get_all_params_values()
        elif self.best_valid_epoch + self.patience < current_epoch:
            print("Early stopping.")
            print("Best valid loss was {:.6f} at epoch {}.".format(
                self.best_valid, self.best_valid_epoch))
            nn.load_params_from(self.best_weights)
            raise StopIteration()
            
class AdjustVariable(object):
    def __init__(self, name, start=0.03, stop=0.001):
        self.name = name
        self.start, self.stop = start, stop
        self.ls = None

    def __call__(self, nn, train_history):
        if self.ls is None:
            self.ls = np.linspace(self.start, self.stop, nn.max_epochs)

        epoch = train_history[-1]['epoch']
        new_value = float32(self.ls[epoch - 1])
        getattr(nn, self.name).set_value(new_value)            
            
def float32(k):
    return np.cast['float32'](k)