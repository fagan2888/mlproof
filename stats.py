import collections
import cPickle as pickle
import lasagne
import numpy as np
import os

from nolearn.lasagne.visualize import draw_to_notebook
from nolearn.lasagne.visualize import plot_loss
from nolearn.lasagne.visualize import plot_conv_weights
from nolearn.lasagne.visualize import plot_conv_activity
from nolearn.lasagne.visualize import plot_occlusion

from sklearn.metrics import classification_report, accuracy_score, roc_curve, auc, precision_recall_fscore_support, f1_score, precision_recall_curve, average_precision_score, zero_one_loss

import matplotlib.pyplot as plt    

import mlproof as mlp


# from http://calebmadrigal.com/display-list-as-table-in-ipython-notebook/
class ListTable(list):
    """ Overridden list class which takes a 2-dimensional list of 
        the form [[1,2,3],[4,5,6]], and renders an HTML Table in 
        IPython Notebook. """
    
    def _repr_html_(self):
        html = ["<table>"]
        for row in self:
            html.append("<tr>")
            
            for col in row:
                html.append("<td>{0}</td>".format(col))
            
            html.append("</tr>")
        html.append("</table>")
        return ''.join(html)


#
# we need to overload our batch iterator
#

from nolearn.lasagne import BatchIterator

class MyTestBatchIterator(BatchIterator):
    def transform(self, Xb, yb):

        # regularize the batch (which is already in the range 0..1)
        if isinstance(Xb, dict):
            # this is for our multi-leg CNN

            for k in Xb:
                Xb[k] = (Xb[k] - .5).astype(np.float32)

        else:

            Xb = Xb - .5
            
        return Xb, yb
#
#
#


class Stats(object):

  @staticmethod
  def quantify_cnns(cnns):

    # load dojo data
    input_image, input_prob, input_gold, input_rhoana, dojo_bbox = mlp.Legacy.read_dojo_data()
    dojo_mean_VI, dojo_median_VI, dojo_VI_s = mlp.Legacy.VI(input_gold, input_rhoana)

    # load cylinder data
    input_image = []
    input_prob = []
    input_rhoana = []
    input_gold = []
    for z in range(250, 300):
        image, prob, mask, gold, rhoana = mlp.Util.read_section('/home/d/data/cylinder/', z, verbose=False)
        
        input_image.append(image)
        input_prob.append(prob)
        input_rhoana.append(rhoana)
        input_gold.append(gold)


    cyl_mean_VI, cyl_median_VI, cyl_VI_s = mlp.Legacy.VI(input_gold, input_rhoana)

    # load patches
    X_train, y_train, X_test_m, y_test_m = mlp.Patch.load('cylinder1', verbose=False)
    X_test_rgba_l, y_test_rgba_l = mlp.Patch.load_rgba_test_only('cylinder1_rgba', border_prefix = 'larger_border', verbose=False)
    X_test_rgba, y_test_rgba = mlp.Patch.load_rgba_test_only('cylinder1_rgba', verbose=False)

    T = ListTable()
    T.append(['',
              '',
              '',
              '',
              '',
              '',
              '',
              '',
              'median VI improvement'
              ])
    T.append(['', 
              'Cost [h]', 
              'Valid. Loss', 
              'Valid. ACC', 
              'Test. ACC', 
              'Prec./Recall', 
              'F1 Score', 
              'ROC AUC', 
              'AC4 (autom.)', 
              'AC4 (guided)', 
              'LCylinder (autom.)', 
              'LCylinder (guided)'
              ])
              # 'Zero-one loss'])

    # store values for ROC plots
    roc_vals = {}
    pc_vals = {}
    cyl_roc_vals = {}
    cyl_pc_vals = {}

    for cnn_name in cnns:
      # load cnn
      if not os.path.exists(cnns[cnn_name]):
        T.append([cnn_name])
        continue

      path = cnns[cnn_name]

      with open(path, 'rb') as f:
        cnn = pickle.load(f)

      cnn.uuid = os.path.basename(os.path.dirname(path))
      cnn_type = cnn.uuid

      # make sure we have the correct test batch iterator
      cnn.batch_iterator_test = MyTestBatchIterator(cnn.batch_iterator_train.batch_size)


      if cnn_type.startswith('RGBA'):
        # this is a rgba network

        if cnn_type.find('large') != -1:
          # large border
          X_test = X_test_rgba_l
          y_test = y_test_rgba_l
          
        else:
          # small border
          X_test = X_test_rgba
          y_test = y_test_rgba        

        test_inputs = X_test
        # input_names.append('RGBA')

      elif cnn_type.startswith('RGB'):
        # this is a RGB net
        X_test = X_test_rgba
        y_test = y_test_rgba
        test_inputs = X_test[:,:-1,:,:]      
        # input_names.append('RGB')

      else:
        # this is mergenet
        X_test = X_test_m
        y_test = y_test_m

        test_inputs = collections.OrderedDict()

        for l in cnn.layers:
          layer_name, layer_type = l
          if layer_type == lasagne.layers.input.InputLayer:
            input_name = layer_name.split('_')[0]
            if input_name == 'binary':
              input_name = 'merged_array'
            if input_name == 'border':
              input_name = 'border_overlap'
              if path.find('larger_border_overlap') != -1:
                input_name = 'larger_border_overlap'

            # input_names.append(layer_name)
            # input_values.append(input_name)
            test_inputs[layer_name] = X_test[input_name]


      test_prediction = cnn.predict(test_inputs)
      test_prediction_prob = cnn.predict_proba(test_inputs)

      # test score
      test_acc = accuracy_score(y_test, test_prediction)

      # ROC/AUC
      fpr, tpr, _ = roc_curve(y_test, test_prediction_prob[:,1])
      roc_auc = auc(fpr, tpr)

      roc_vals[cnn_name] = (fpr, tpr, roc_auc)

      # prec./recall
      precision, recall, _, _ = precision_recall_fscore_support(y_test, test_prediction)
      prec_recall = str(round((precision[0] + precision[1])/2,3)) + '/' + str(round((recall[0] + recall[1])/2,3))
      f1_score_val = f1_score(y_test, test_prediction)
      p, c, _ = precision_recall_curve(y_test, test_prediction_prob[:,1])
      pc_auc = average_precision_score(y_test, test_prediction_prob[:,1], average='micro')
      pc_vals[cnn_name] = (p, c, pc_auc)

      #
      patience_counter = cnn.on_epoch_finished[2].patience
      best_epoch = cnn.train_history_[-2-patience_counter]
      duration = best_epoch['dur']
      epoch = best_epoch['epoch']
      valid_acc = best_epoch['valid_accuracy']
      valid_loss = best_epoch['valid_loss']
      cost = (epoch * duration) / 3600.

      output_folder = '/home/d/netstats/'+cnn.uuid+'/'
      # AC4 (automatic)
      vi_file = output_folder + '/dojo_vi_95.p'
      if os.path.exists(vi_file):
        with open(vi_file, 'rb') as f:
          vi = pickle.load(f)        
        ac4_autom = dojo_median_VI-vi[1]
      else:
        ac4_autom = -1

      # AC4 (guided)
      vi_file = output_folder + '/dojo_vi_simuser.p'
      if os.path.exists(vi_file):
        with open(vi_file, 'rb') as f:
          vi = pickle.load(f)        
        ac4_guided = dojo_median_VI-vi[1]
      else:
        ac4_guided = -1    

      # Cylinder (automatic)
      vi_file = output_folder + '/cylinder_vi_95.p'
      if os.path.exists(vi_file):
        with open(vi_file, 'rb') as f:
          vi = pickle.load(f)        
        cylinder_autom = cyl_median_VI-vi[1]
      else:
        cylinder_autom = -1
      # Cylinder (guided)
      vi_file = output_folder + '/cylinder_vi_simuser.p'
      if os.path.exists(vi_file):
        with open(vi_file, 'rb') as f:
          vi = pickle.load(f)        
        cylinder_guided = cyl_median_VI-vi[1]
      else:
        cylinder_guided = -1

      # load fixes for second ROC plot
      zero_one_loss = -1
      cylinder_fixes_simuser_file = output_folder + '/cylinder_fixes_simuser.p'
      if os.path.exists(cylinder_fixes_simuser_file):
        with open(cylinder_fixes_simuser_file, 'rb') as f:
          cylinder_sim_user_fixes = pickle.load(f)   

        y_test_fixes = [v[0] for v in cylinder_sim_user_fixes]
        y_pred_fixes = [v[1] for v in cylinder_sim_user_fixes]
        fpr, tpr, _ = roc_curve(y_test_fixes, y_pred_fixes)
        roc_auc = auc(fpr, tpr)    
        cyl_roc_vals[cnn_name] = (fpr, tpr, roc_auc)

        p, c, _ = precision_recall_curve(y_test_fixes, y_pred_fixes)
        pc_auc = average_precision_score(y_test_fixes, y_pred_fixes, average='micro')
        cyl_pc_vals[cnn_name] = (p, c, pc_auc)        

        # zero_one_loss = zero_one_loss(y_test_fixes, y_pred_fixes, normalize=True)

      T.append([
                cnn_name,
                round(cost,3),
                round(valid_loss,3),
                round(valid_acc,3),
                round(test_acc,3),
                prec_recall,
                round(f1_score_val,3),
                round(roc_auc,3),
                round(ac4_autom,3),
                round(ac4_guided,3),
                round(cylinder_autom,3),
                round(cylinder_guided,3)
                # round(zero_one_loss,3)
               ])


    mlp.Legacy.plot_roc(roc_vals, title='Classifier ROC Comparison')
    mlp.Legacy.plot_roc(cyl_roc_vals, title='Guided Proofreading ROC Comparison')
    mlp.Legacy.plot_pc(pc_vals, title='Classifier Precision/Recall Comparison')
    mlp.Legacy.plot_pc(cyl_pc_vals, title='Guided Proofreading Precision/Recall Comparison')


    return T

  @staticmethod
  def compare(cnns):

    roc_vals = {}
    pc_vals = {}

    # load patches
    X_train, y_train, X_test_m, y_test_m = mlp.Patch.load('cylinder1', verbose=False)
    X_test_rgba_l, y_test_rgba_l = mlp.Patch.load_rgba_test_only('cylinder1_rgba', border_prefix = 'larger_border', verbose=False)
    X_test_rgba, y_test_rgba = mlp.Patch.load_rgba_test_only('cylinder1_rgba', verbose=False)


    for cnn_name in cnns:
      # load cnn
      path = cnns[cnn_name]

      with open(path, 'rb') as f:
        cnn = pickle.load(f)

      cnn.uuid = os.path.basename(os.path.dirname(path))
      cnn_type = cnn.uuid

      # make sure we have the correct test batch iterator
      cnn.batch_iterator_test = MyTestBatchIterator(cnn.batch_iterator_train.batch_size)


      if cnn_type.startswith('RGBA'):
        # this is a rgba network

        if cnn_type.find('large') != -1:
          # large border
          X_test = X_test_rgba_l
          y_test = y_test_rgba_l
          
        else:
          # small border
          X_test = X_test_rgba
          y_test = y_test_rgba        

        test_inputs = X_test
        # input_names.append('RGBA')

      elif cnn_type.startswith('RGB'):
        # this is a RGB net
        X_test = X_test_rgba
        y_test = y_test_rgba
        test_inputs = X_test[:,:-1,:,:]      
        # input_names.append('RGB')

      else:
        # this is mergenet
        X_test = X_test_m
        y_test = y_test_m

        test_inputs = collections.OrderedDict()

        for l in cnn.layers:
          layer_name, layer_type = l
          if layer_type == lasagne.layers.input.InputLayer:
            input_name = layer_name.split('_')[0]
            if input_name == 'binary':
              input_name = 'merged_array'
            if input_name == 'border':
              input_name = 'border_overlap'
              if path.find('larger_border_overlap') != -1:
                input_name = 'larger_border_overlap'

            # input_names.append(layer_name)
            # input_values.append(input_name)
            test_inputs[layer_name] = X_test[input_name]


      test_prediction = cnn.predict(test_inputs)
      test_prediction_prob = cnn.predict_proba(test_inputs)

      # ROC/AUC
      fpr, tpr, _ = roc_curve(y_test, test_prediction_prob[:,1])
      roc_auc = auc(fpr, tpr)

      roc_vals[cnn_name] = (fpr, tpr, roc_auc)

      # prec./recall
      precision, recall, _, _ = precision_recall_fscore_support(y_test, test_prediction)
      prec_recall = str(round((precision[0] + precision[1])/2,3)) + '/' + str(round((recall[0] + recall[1])/2,3))
      f1_score_val = f1_score(y_test, test_prediction)
      p, c, _ = precision_recall_curve(y_test, test_prediction_prob[:,1])
      pc_auc = average_precision_score(y_test, test_prediction_prob[:,1], average='micro')
      pc_vals[cnn_name] = (p, c, pc_auc)

    mlp.Legacy.plot_roc(roc_vals, filename='/home/d/netstats/roc_plot.pdf')
    mlp.Legacy.plot_roc_zoom(roc_vals, filename='/home/d/netstats/roc_plot_zoom.pdf')
    mlp.Legacy.plot_pc(pc_vals, filename='/home/d/netstats/pr_plot.pdf')
    mlp.Legacy.plot_pc_zoom(pc_vals, filename='/home/d/netstats/pr_plot_zoom.pdf')

    return roc_vals


  @staticmethod
  def load_cnn(path, cnn_type=None):

    # load cnn
    with open(path, 'rb') as f:
      cnn = pickle.load(f)    

    # make sure we have the correct test batch iterator
    # cnn.batch_iterator_test = MyTestBatchIterator(cnn.batch_iterator_train.batch_size)

    if cnn_type == None:
      cnn_type = os.path.basename(os.path.dirname(path))

    input_names = []
    input_values = []
    if cnn_type.startswith('RGBA'):
      # this is a rgba network

      if cnn_type.find('large') != -1:
        # large border
        X_test, y_test = mlp.Patch.load_rgba_test_only('cylinder1_rgba', border_prefix = 'larger_border')
        
      else:
        # small border
        X_test, y_test = mlp.Patch.load_rgba_test_only('cylinder1_rgba')

      test_inputs = X_test
      input_names.append('RGBA')

    elif cnn_type.startswith('RGB'):
      # this is a RGB net
      X_test, y_test = mlp.Patch.load_rgb_test_only('cylinder2_rgb')
      # test_inputs = X_test[:,:-1,:,:]   
      test_inputs = X_test   
      input_names.append('RGB')

    else:
      # load patches
      X_train, y_train, X_test, y_test = mlp.Patch.load('cylinder2')

      test_inputs = collections.OrderedDict()

      for l in cnn.layers:
        layer_name, layer_type = l
        if layer_type == lasagne.layers.input.InputLayer:
          input_name = layer_name.split('_')[0]
          if input_name == 'binary':
            input_name = 'merged_array'
          if input_name == 'border':
            input_name = 'border_overlap'
            if path.find('larger_border_overlap') != -1:
              input_name = 'larger_border_overlap'

          input_names.append(layer_name)
          input_values.append(input_name)
          test_inputs[layer_name] = X_test[input_name]

      print 'Using test set:', input_values

    

    # calc F1
    test_prediction = cnn.predict(test_inputs)
    test_prediction_prob = cnn.predict_proba(test_inputs)
    print
    print 'Precision/Recall:'
    print classification_report(y_test, test_prediction)

    # calc test accuracy
    test_acc = cnn.score(test_inputs, y_test)
    acc_score = accuracy_score(y_test, test_prediction)
    print 'Test Accuracy:', test_acc
    print 'Accuracy Score:', acc_score

    # ROC/AUC
    fpr, tpr, _ = roc_curve(y_test, test_prediction_prob[:,1])
    roc_auc = auc(fpr, tpr)

    # attach patch selection
    cnn.input_names = input_names
    cnn.input_values = input_values
    cnn.uuid = cnn_type#os.path.basename(os.path.dirname(path))

    
    # plot loss    
    output_folder = '/home/d/netstats/'+cnn.uuid+'/'
    if not os.path.exists(output_folder):
      os.makedirs(output_folder)
    font = {'family' : 'normal',
    #         'weight' : 'bold',
            'size'   : 26}
    plt.rc('font', **font)      
    plt.figure(figsize=(22,22))

    loss_plot = plot_loss(cnn)
    loss_plot.savefig(output_folder+'/loss.pdf')

    data = {}
    data['CNN'] = (fpr, tpr, roc_auc)
    mlp.Legacy.plot_roc(data, output_folder+'/cnn_roc.pdf')

    return cnn

  @staticmethod
  def run_dojo_xp(cnn):

    # load dojo data
    input_image, input_prob, input_gold, input_rhoana, dojo_bbox = mlp.Legacy.read_dojo_data()


    original_mean_VI, original_median_VI, original_VI_s = mlp.Legacy.VI(input_gold, input_rhoana)

    # output folder for anything to store
    output_folder = '/home/d/netstats/'+cnn.uuid+'/'
    if not os.path.exists(output_folder):
      os.makedirs(output_folder)

    # find merge errors, if we did not generate them before
    merge_error_file = output_folder+'/merge_errors.p'
    if os.path.exists(merge_error_file):
      print 'Loading merge errors from file..'
      with open(merge_error_file, 'rb') as f:
        merge_errors = pickle.load(f)
    else:
      print 'Finding Top 5 merge errors..'
      merge_errors = mlp.Legacy.get_top5_merge_errors(cnn, input_image, input_prob, input_rhoana)
      with open(merge_error_file, 'wb') as f:
        pickle.dump(merge_errors, f)

    print len(merge_errors), ' merge errors found.'

    # we need to create a bigM for the dojo volume
    bigM_dojo_file = output_folder + '/bigM_dojo.p'
    if os.path.exists(bigM_dojo_file):
      print 'Loading dojo bigM from file..'
      with open(bigM_dojo_file, 'rb') as f:
        bigM_dojo = pickle.load(f)
    else:
      print 'Creating dojo bigM..'
      bigM_dojo = mlp.Legacy.create_bigM_without_mask(cnn, input_image, input_prob, input_rhoana, verbose=False)
      with open(bigM_dojo_file, 'wb') as f:
        pickle.dump(bigM_dojo, f)    



    print
    dojo_vi_95_file = output_folder + '/dojo_vi_95.p'
    if os.path.exists(dojo_vi_95_file):
      print 'Loading merge errors p < .05 and split errors p > .95 from file..'
      with open(dojo_vi_95_file, 'rb') as f:
        dojo_vi_95 = pickle.load(f)
    else:      
      #
      # perform merge correction with p < .05
      #
      print 'Correcting merge errors with p < .05'
      bigM_dojo_05, corrected_rhoana_05 = mlp.Legacy.perform_auto_merge_correction(cnn, bigM_dojo, input_image, input_prob, input_rhoana, merge_errors, .05)

      print '   Mean VI improvement', original_mean_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[0]
      print '   Median VI improvement', original_median_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[1]

      #
      # perform split correction with p > .95
      #
      print 'Correcting split errors with p > .95'
      bigM_dojo_after_95, out_dojo_volume_after_auto_95, dojo_auto_fixes_95, dojo_auto_vi_s_95 = mlp.Legacy.splits_global_from_M_automatic(cnn, bigM_dojo_05, input_image, input_prob, corrected_rhoana_05, input_gold, sureness_threshold=.95)

      dojo_vi_95 = mlp.Legacy.VI(input_gold, out_dojo_volume_after_auto_95)

      with open(dojo_vi_95_file, 'wb') as f:
        pickle.dump(dojo_vi_95, f)

    print '   Mean VI improvement', original_mean_VI-dojo_vi_95[0]
    print '   Median VI improvement', original_median_VI-dojo_vi_95[1]




    print
    dojo_vi_99_file = output_folder + '/dojo_vi_99.p'
    if os.path.exists(dojo_vi_99_file):
      print 'Loading merge errors p < .01 and split errors p > .99 from file..'
      with open(dojo_vi_99_file, 'rb') as f:
        dojo_vi_99 = pickle.load(f)
    else:      
      #
      # perform merge correction with p < .01
      #
      print 'Correcting merge errors with p < .01'
      bigM_dojo_01, corrected_rhoana_01 = mlp.Legacy.perform_auto_merge_correction(cnn, bigM_dojo, input_image, input_prob, input_rhoana, merge_errors, .01)

      print '   Mean VI improvement', original_mean_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_01)[0]
      print '   Median VI improvement', original_median_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_01)[1]

      #
      # perform split correction with p > .99
      #
      print 'Correcting split errors with p > .99'
      bigM_dojo_after_99, out_dojo_volume_after_auto_99, dojo_auto_fixes_99, dojo_auto_vi_s_99 = mlp.Legacy.splits_global_from_M_automatic(cnn, bigM_dojo_01, input_image, input_prob, corrected_rhoana_01, input_gold, sureness_threshold=.99)

      dojo_vi_99 = mlp.Legacy.VI(input_gold, out_dojo_volume_after_auto_99)

      with open(dojo_vi_99_file, 'wb') as f:
        pickle.dump(dojo_vi_99, f)

    print '   Mean VI improvement', original_mean_VI-dojo_vi_99[0]
    print '   Median VI improvement', original_median_VI-dojo_vi_99[1]




    print
    dojo_vi_simuser_file = output_folder + '/dojo_vi_simuser.p'
    if os.path.exists(dojo_vi_simuser_file):
      print 'Loading merge errors and split errors (simulated user) from file..'
      with open(dojo_vi_simuser_file, 'rb') as f:
        dojo_vi_simuser = pickle.load(f)
    else:
      #
      # perform merge correction with simulated user
      #
      print 'Correcting merge errors by simulated user (er=0)'
      bigM_dojo_simuser, corrected_rhoana_sim_user, sim_user_fixes = mlp.Legacy.perform_sim_user_merge_correction(cnn, bigM_dojo, input_image, input_prob, input_rhoana, input_gold, merge_errors)
      
      print '   Mean VI improvement', original_mean_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_sim_user)[0]    
      print '   Median VI improvement', original_median_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_sim_user)[1]
      
      #
      # perform split correction with simulated user
      #
      print 'Correcting split errors by simulated user (er=0)'
      bigM_dojo_after, out_dojo_volume_after_sim_user, dojo_sim_user_fixes, dojo_sim_user_vi_s = mlp.Legacy.splits_global_from_M(cnn, bigM_dojo_simuser, input_image, input_prob, corrected_rhoana_sim_user, input_gold, hours=.5)

      dojo_vi_simuser = mlp.Legacy.VI(input_gold, out_dojo_volume_after_sim_user)

      with open(dojo_vi_simuser_file, 'wb') as f:
        pickle.dump(dojo_vi_simuser, f)      

    print '   Mean VI improvement', original_mean_VI-dojo_vi_simuser[0]
    print '   Median VI improvement', original_median_VI-dojo_vi_simuser[1]

    
    print
    dojo_vi_simuser_er_file = output_folder + '/dojo_vi_simuser_er.p'
    if os.path.exists(dojo_vi_simuser_er_file):
      print 'Loading merge errors and split errors (simulated user) with error rates from file..'
      with open(dojo_vi_simuser_er_file, 'rb') as f:
        dojo_vi_simuser_er = pickle.load(f)
    else:
      #
      # Simulated user split correction with error rate
      #
      print '   Re-running simulated user with er=0 .. 0.2'
      dojo_vi_simuser_er = collections.OrderedDict()
      for error_rate in range(0,21):
        error_rate /= 100.
        # print '---',error_rate
        bigM_dojo_after, out_dojo_volume_after_sim_user, dojo_sim_user_fixes, dojo_sim_user_vi_s = mlp.Legacy.splits_global_from_M(cnn, bigM_dojo, input_image, input_prob, input_rhoana, input_gold, hours=.5, error_rate=error_rate)

        # append the mean VI
        dojo_vi_simuser_er[str(error_rate)] = mlp.Legacy.VI(input_gold, out_dojo_volume_after_sim_user)[1]

      with open(dojo_vi_simuser_er_file, 'wb') as f:
        pickle.dump(dojo_vi_simuser_er, f)



    #
    #
    # DOJO VIs
    #
    #
    dojo_input_vi = mlp.Legacy.VI(input_gold, input_rhoana)[2]
    dojo_best_user = [0.3764043166,
                      0.3516472472,
                      0.4079547444,
                      0.4530306854,
                      0.489459557,
                      0.4783714198,
                      0.4691797846,
                      0.4852945057,
                      0.4989719721,
                      0.4631116968]

    dojo_avg_user = [0.4731860794,
                     0.4412143846,
                     0.4645102603,
                     0.4790327986,
                     0.5483534853,
                     0.5209529753,
                     0.5614397773,
                     0.5669964498,
                     0.6037881064,
                     0.5986637472]

    dojo_novice = [0.37012190195707095,
                   0.38968960153287835,
                   0.37045672764672943,
                   0.38191441070762,
                   0.45717155397457265,
                   0.4307223374738305,
                   0.46325236818430504,
                   0.5049116191382206,
                   0.45915778345523783,
                   0.5901800985629162]

    # josh
    dojo_expert1 = [0.37484603520770676,
                    0.3939621266824016,
                    0.3896524948878737,
                    0.39639562518511084,
                    0.4477210348104004,
                    0.4647934798574145,
                    0.4647357412387576,
                    0.4583758825458508,
                    0.42396064070850503,
                    0.4060052118497355]

    # alyssa
    dojo_expert2 = [0.36955775659747747,
                    0.39250293829836735,
                    0.3688303634072678,
                    0.37744240803449625,
                    0.40022644067826807,
                    0.3815527838331203,
                    0.4472774009966649,
                    0.44162415508056707,
                    0.4729849772418282,
                    0.4966401210922369]

    random_recommendations = [0.4595423295850365,
                              0.4308474043605237,
                              0.3986397439416596,
                              0.39881363108964063,
                              0.4774106038339303,
                              0.47744847314733896,
                              0.5331778295505849,
                              0.5657477626512799,
                              0.6298385736857668,
                              0.5383586601809531]


    data = collections.OrderedDict()
    data['Automatic\nSegmentation'] = dojo_input_vi
    data['Dojo\n(avg. user)'] = dojo_avg_user
    data['Dojo\n(best user)'] = dojo_best_user
    data['Novice    \nUser'] = dojo_novice
    data['Expert     \nUser 1'] = dojo_expert1
    data['Expert     \nUser 2'] = dojo_expert2
    data['Simulated   \nUser   '] = dojo_vi_simuser[2]
    data['Random\nRecommen-\ndations'] = random_recommendations
    data['Automatic\nCorrections\n(p=.95)'] = dojo_vi_95[2]
    data['Automatic\nCorrections\n(p=.99)'] = dojo_vi_99[2]


    mlp.Legacy.plot_vis(data, output_folder+'/dojo_vi.pdf')

    #
    # simple VI plot
    #
    data = collections.OrderedDict()
    data['Initial\nSegmentation'] = dojo_input_vi
    data['Automatic\nCorrections'] = dojo_vi_95[2]
    data['Dojo       '] = dojo_best_user
    data['Guided    \n(Novice)    '] = dojo_novice
    expert_sum = []
    for i,d in enumerate(dojo_expert1):
      expert_sum.append((dojo_expert1[i]+dojo_expert2[i])/2.)
    data['Guided    \n(Expert)   '] = expert_sum
    data['Guided\n(Simulated)'] = dojo_vi_simuser[2]
    mlp.Legacy.plot_vis(data, output_folder+'/dojo_vi_simple3.pdf')

    #
    # simple VI plot
    #
    data = collections.OrderedDict()
    data['Initial\nSegmentation'] = dojo_input_vi
    data['Automatic\nCorrections'] = dojo_vi_95[2]
    data['Dojo       '] = dojo_best_user
    expert_sum = []
    for i,d in enumerate(dojo_expert1):
      expert_sum.append((dojo_expert1[i]+dojo_expert2[i])/2.)
    # data['Guided    \n(Novice)   '] = dojo_novice
    data['Guided     '] = expert_sum
    # data['Guided\n(Simulated)'] = dojo_vi_simuser[2]
    mlp.Legacy.plot_vis(data, output_folder+'/dojo_vi_simple2.pdf')




    mlp.Legacy.plot_vis_error_rate(dojo_vi_simuser_er, np.median(dojo_avg_user), np.median(dojo_best_user), output_folder+'/dojo_errorrate.pdf')





  @staticmethod
  def run_cylinder_xp(cnn):

    # load cylinder data
    input_image = []
    input_prob = []
    input_rhoana = []
    input_gold = []
    for z in range(250, 300):
        image, prob, mask, gold, rhoana = mlp.Util.read_section('/home/d/data/cylinder/', z, verbose=False)
        
        input_image.append(image)
        input_prob.append(prob)
        input_rhoana.append(rhoana)
        input_gold.append(gold)


    original_mean_VI, original_median_VI, original_VI_s = mlp.Legacy.VI(input_gold, input_rhoana)

    print 'Original median VI', original_median_VI

    # output folder for anything to store
    output_folder = '/home/d/netstats/'+cnn.uuid+'/'
    if not os.path.exists(output_folder):
      os.makedirs(output_folder)






    ### SKIPPING MERGE FOR NOW
    # # find merge errors, if we did not generate them before
    # merge_error_file = output_folder+'/merge_errors.p'
    # if os.path.exists(merge_error_file):
    #   print 'Loading merge errors from file..'
    #   with open(merge_error_file, 'rb') as f:
    #     merge_errors = pickle.load(f)
    # else:
    #   print 'Finding Top 5 merge errors..'
    #   merge_errors = mlp.Legacy.get_top5_merge_errors(cnn, input_image, input_prob, input_rhoana)
    #   with open(merge_error_file, 'wb') as f:
    #     pickle.dump(merge_errors, f)

    # print len(merge_errors), ' merge errors found.'
    ####

    # we need to create a bigM for the cylinder volume
    bigM_cylinder_file = output_folder + '/bigM_cylinder.p'
    if os.path.exists(bigM_cylinder_file):
      print 'Loading cylinder bigM from file..'
      with open(bigM_cylinder_file, 'rb') as f:
        bigM_cylinder = pickle.load(f)
    else:
      print 'Creating cylinder bigM..'
      bigM_cylinder = mlp.Legacy.create_bigM_without_mask(cnn, input_image, input_prob, input_rhoana, verbose=True, max=1000000)
      with open(bigM_cylinder_file, 'wb') as f:
        pickle.dump(bigM_cylinder, f)    




    print
    cylinder_vi_95_file = output_folder + '/cylinder_vi_95.p'
    cylinder_vi_auto_95_fixes_file = output_folder + '/cylinder_vi_95_fixes.p'
    cylinder_auto_vis_95_file = output_folder + '/cylinder_auto_vis_95.p'
    if os.path.exists(cylinder_vi_95_file):
      print 'Loading merge errors p < .05 and split errors p > .95 from file..'
      with open(cylinder_vi_95_file, 'rb') as f:
        cylinder_vi_95 = pickle.load(f)
      with open(cylinder_auto_vis_95_file, 'rb') as f:
        cylinder_auto_vi_s_95 = pickle.load(f)
    else:      
      # #
      # # perform merge correction with p < .05
      # #
      # print 'Correcting merge errors with p < .05'
      # bigM_dojo_05, corrected_rhoana_05 = mlp.Legacy.perform_auto_merge_correction(cnn, bigM_dojo, input_image, input_prob, input_rhoana, merge_errors, .05)

      # print '   Mean VI improvement', original_mean_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[0]
      # print '   Median VI improvement', original_median_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[1]

      #
      # perform split correction with p > .95
      #
      print 'Correcting split errors with p > .95'
      bigM_cylinder_05 = bigM_cylinder
      corrected_rhoana_05 = input_rhoana
      bigM_cylinder_after_95, out_cylinder_volume_after_auto_95, cylinder_auto_fixes_95, cylinder_auto_vi_s_95 = mlp.Legacy.splits_global_from_M_automatic(cnn, bigM_cylinder_05, input_image, input_prob, corrected_rhoana_05, input_gold, sureness_threshold=.95)

      cylinder_vi_95 = mlp.Legacy.VI(input_gold, out_cylinder_volume_after_auto_95)

      with open(cylinder_vi_95_file, 'wb') as f:
        pickle.dump(cylinder_vi_95, f)

      with open(cylinder_vi_auto_95_fixes_file, 'wb') as f:
        pickle.dump(cylinder_auto_fixes_95, f)

      with open(cylinder_auto_vis_95_file, 'wb') as f:
        pickle.dump(cylinder_auto_vi_s_95, f)        

    print '   Mean VI improvement', original_mean_VI-cylinder_vi_95[0]
    print '   Median VI improvement', original_median_VI-cylinder_vi_95[1]





    print
    cylinder_vi_99_file = output_folder + '/cylinder_vi_99.p'
    if os.path.exists(cylinder_vi_99_file):
      print 'Loading merge errors p < .01 and split errors p > .99 from file..'
      with open(cylinder_vi_99_file, 'rb') as f:
        cylinder_vi_99 = pickle.load(f)
    else:      
      # #
      # # perform merge correction with p < .01
      # #
      # print 'Correcting merge errors with p < .01'
      # bigM_dojo_05, corrected_rhoana_05 = mlp.Legacy.perform_auto_merge_correction(cnn, bigM_dojo, input_image, input_prob, input_rhoana, merge_errors, .05)

      # print '   Mean VI improvement', original_mean_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[0]
      # print '   Median VI improvement', original_median_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[1]

      #
      # perform split correction with p > .99
      #
      print 'Correcting split errors with p > .99'
      bigM_cylinder_01 = bigM_cylinder
      corrected_rhoana_01 = input_rhoana
      bigM_cylinder_after_99, out_cylinder_volume_after_auto_99, cylinder_auto_fixes_99, cylinder_auto_vi_s_99 = mlp.Legacy.splits_global_from_M_automatic(cnn, bigM_cylinder_01, input_image, input_prob, corrected_rhoana_01, input_gold, sureness_threshold=.99)

      cylinder_vi_99 = mlp.Legacy.VI(input_gold, out_cylinder_volume_after_auto_99)

      with open(cylinder_vi_99_file, 'wb') as f:
        pickle.dump(cylinder_vi_99, f)

    print '   Mean VI improvement', original_mean_VI-cylinder_vi_99[0]
    print '   Median VI improvement', original_median_VI-cylinder_vi_99[1]


    print
    cylinder_vi_0_file = output_folder + '/cylinder_vi_0.p'
    cylinder_vi_auto_0_fixes_file = output_folder + '/cylinder_vi_0_fixes.p'
    cylinder_auto_vis_0_file = output_folder + '/cylinder_auto_vis_0.p'    
    if os.path.exists(cylinder_vi_0_file):
      print 'Loading split errors p >= .0 from file..'
      with open(cylinder_vi_0_file, 'rb') as f:
        cylinder_vi_0 = pickle.load(f)
      with open(cylinder_vi_auto_0_fixes_file, 'rb') as f:
        cylinder_auto_fixes_00 = pickle.load(f)
      with open(cylinder_auto_vis_0_file, 'rb') as f:
        cylinder_auto_vi_s_00 = pickle.load(f)


    else:      
      # #
      # # perform merge correction with p < .01
      # #
      # print 'Correcting merge errors with p < .01'
      # bigM_dojo_05, corrected_rhoana_05 = mlp.Legacy.perform_auto_merge_correction(cnn, bigM_dojo, input_image, input_prob, input_rhoana, merge_errors, .05)

      # print '   Mean VI improvement', original_mean_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[0]
      # print '   Median VI improvement', original_median_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[1]

      #
      # perform split correction with p > .99
      #
      print 'Correcting split errors with p >= .0'
      bigM_cylinder_00 = bigM_cylinder
      corrected_rhoana_00 = input_rhoana
      bigM_cylinder_after_00, out_cylinder_volume_after_auto_00, cylinder_auto_fixes_00, cylinder_auto_vi_s_00 = mlp.Legacy.splits_global_from_M_automatic(cnn, bigM_cylinder_00, input_image, input_prob, corrected_rhoana_00, input_gold, sureness_threshold=.0)

      cylinder_vi_0 = mlp.Legacy.VI(input_gold, out_cylinder_volume_after_auto_00)

      with open(cylinder_vi_0_file, 'wb') as f:
        pickle.dump(cylinder_vi_0, f)

      with open(cylinder_vi_auto_0_fixes_file, 'wb') as f:
        pickle.dump(cylinder_auto_fixes_00, f)

      with open(cylinder_auto_vis_0_file, 'wb') as f:
        pickle.dump(cylinder_auto_vi_s_00, f)      

    print '   Mean VI improvement', original_mean_VI-cylinder_vi_0[0]
    print '   Median VI improvement', original_median_VI-cylinder_vi_0[1]



    print
    cylinder_vi_simuser_file = output_folder + '/cylinder_vi_simuser.p'
    cylinder_fixes_simuser_file = output_folder + '/cylinder_fixes_simuser.p'
    cylinder_vis_simuser_file = output_folder + '/cylinder_vi_s_simuser.p'
    if os.path.exists(cylinder_vi_simuser_file):
      print 'Loading merge errors and split errors (simulated user) from file..'
      with open(cylinder_vi_simuser_file, 'rb') as f:
        cylinder_vi_simuser = pickle.load(f)
      with open(cylinder_fixes_simuser_file, 'rb') as f:
        cylinder_sim_user_fixes = pickle.load(f)
      with open(cylinder_vis_simuser_file, 'rb') as f:
        cylinder_sim_user_vi_s = pickle.load(f)


    else:
      # #
      # # perform merge correction with simulated user
      # #
      # print 'Correcting merge errors by simulated user (er=0)'
      # bigM_dojo_simuser, corrected_rhoana_sim_user, sim_user_fixes = mlp.Legacy.perform_sim_user_merge_correction(cnn, bigM_dojo, input_image, input_prob, input_rhoana, input_gold, merge_errors)
      
      # print '   Mean VI improvement', original_mean_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_sim_user)[0]    
      # print '   Median VI improvement', original_median_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_sim_user)[1]
      
      #
      # perform split correction with simulated user
      #
      print 'Correcting split errors by simulated user (er=0)'
      bigM_cylinder_simuser = bigM_cylinder
      corrected_rhoana_sim_user = input_rhoana
      bigM_cylinder_after, out_cylinder_volume_after_sim_user, cylinder_sim_user_fixes, cylinder_sim_user_vi_s = mlp.Legacy.splits_global_from_M(cnn, bigM_cylinder_simuser, input_image, input_prob, corrected_rhoana_sim_user, input_gold, hours=-1)

      cylinder_vi_simuser = mlp.Legacy.VI(input_gold, out_cylinder_volume_after_sim_user)

      with open(cylinder_vi_simuser_file, 'wb') as f:
        pickle.dump(cylinder_vi_simuser, f)      

      with open(cylinder_vis_simuser_file, 'wb') as f:
        pickle.dump(cylinder_sim_user_vi_s, f)

      with open(cylinder_fixes_simuser_file, 'wb') as f:
        pickle.dump(cylinder_sim_user_fixes, f)

    print '   Mean VI improvement', original_mean_VI-cylinder_vi_simuser[0]
    print '   Median VI improvement', original_median_VI-cylinder_vi_simuser[1]


    data = collections.OrderedDict()
    data['Automatic\nSegmentation'] = mlp.Legacy.VI(input_gold, input_rhoana)[2]
    data['Simulated   \nUser   '] = cylinder_vi_simuser[2]
    data['Automatic\nCorrections\n(p=.95)'] = cylinder_vi_95[2]
    data['Automatic\nCorrections\n(p=.99)'] = cylinder_vi_99[2]


    mlp.Legacy.plot_vis(data, output_folder+'/cylinder_vi.pdf')

    #
    # Simple VI boxplot
    #
    data = collections.OrderedDict()
    data['Initial\nSegmentation'] = mlp.Legacy.VI(input_gold, input_rhoana)[2]
    data['Automatic\nCorrections'] = cylinder_vi_95[2]    
    data['Guided\n(Simulated)'] = cylinder_vi_simuser[2]

    mlp.Legacy.plot_vis(data, output_folder+'/cylinder_vi_simple.pdf')




    proofread_vis = [original_VI_s] + cylinder_sim_user_vi_s
    vi_s_per_correction = [np.median(proofread_vis[0])]
    for m in proofread_vis[1:]:
        for i in range(30*12):
            vi_s_per_correction.append(np.median(m))

    mlp.Legacy.plot_vi_simuser(vi_s_per_correction, output_folder+'/cylinder_simuser_vi.pdf')

    proofread_vis_auto = [original_VI_s] + cylinder_auto_vi_s_00
    vi_s_per_correction_auto = [np.median(proofread_vis_auto[0])]
    for m in proofread_vis_auto[1:]:
        for i in range(30*12):
            vi_s_per_correction_auto.append(np.median(m))

    # mlp.Legacy.plot_vi_combined(vi_s_per_correction_auto, vi_s_per_correction, output_folder+'/cylinder_combined_vi.pdf')
    mlp.Legacy.plot_vi_combined_no_interpolation(vi_s_per_correction_auto, vi_s_per_correction, output_folder+'/cylinder_combined_vi_no_interpolation.pdf')


    data = {}
    y_text_fixes = [v[0] for v in cylinder_sim_user_fixes]
    y_pred_fixes = [v[1] for v in cylinder_sim_user_fixes]
    fpr, tpr, _ = roc_curve(y_text_fixes, y_pred_fixes)
    roc_auc = auc(fpr, tpr)    
    data['Cylinder Fixes'] = (fpr, tpr, roc_auc)
    mlp.Legacy.plot_roc(data, output_folder+'/cylinder_roc.pdf')


  @staticmethod
  def run_cylinder_new_xp(cnn):

    # load cylinder data
    input_image = []
    input_prob = []
    input_rhoana = []
    input_gold = []
    for z in range(250, 300):
        image, prob, mask, gold, rhoana = mlp.Util.read_section('/home/d/data/cylinderNEW/', z, verbose=False)

        input_image.append(image)
        input_prob.append(255.-prob)
        input_rhoana.append(rhoana)
        input_gold.append(gold)


    original_mean_VI, original_median_VI, original_VI_s = mlp.Legacy.VI(input_gold, input_rhoana)

    print 'Original median VI', original_median_VI

    # output folder for anything to store
    output_folder = '/home/d/netstatsNEW/'+cnn.uuid+'/'
    if not os.path.exists(output_folder):
      os.makedirs(output_folder)






    ### SKIPPING MERGE FOR NOW
    # # find merge errors, if we did not generate them before
    # merge_error_file = output_folder+'/merge_errors.p'
    # if os.path.exists(merge_error_file):
    #   print 'Loading merge errors from file..'
    #   with open(merge_error_file, 'rb') as f:
    #     merge_errors = pickle.load(f)
    # else:
    #   print 'Finding Top 5 merge errors..'
    #   merge_errors = mlp.Legacy.get_top5_merge_errors(cnn, input_image, input_prob, input_rhoana)
    #   with open(merge_error_file, 'wb') as f:
    #     pickle.dump(merge_errors, f)

    # print len(merge_errors), ' merge errors found.'
    ####

    # we need to create a bigM for the cylinder volume
    bigM_cylinder_file = output_folder + '/bigM_cylinder.p'
    if os.path.exists(bigM_cylinder_file):
      print 'Loading cylinder bigM from file..'
      with open(bigM_cylinder_file, 'rb') as f:
        bigM_cylinder = pickle.load(f)
    else:
      print 'Creating cylinder bigM..'
      bigM_cylinder = mlp.Legacy.create_bigM_without_mask(cnn, input_image, input_prob, input_rhoana, verbose=True, max=1000000)
      with open(bigM_cylinder_file, 'wb') as f:
        pickle.dump(bigM_cylinder, f)    




    print
    cylinder_vi_95_file = output_folder + '/cylinder_vi_95.p'
    cylinder_vi_auto_95_fixes_file = output_folder + '/cylinder_vi_95_fixes.p'
    cylinder_auto_vis_95_file = output_folder + '/cylinder_auto_vis_95.p'
    if os.path.exists(cylinder_vi_95_file):
      print 'Loading merge errors p < .05 and split errors p > .95 from file..'
      with open(cylinder_vi_95_file, 'rb') as f:
        cylinder_vi_95 = pickle.load(f)
      with open(cylinder_auto_vis_95_file, 'rb') as f:
        cylinder_auto_vi_s_95 = pickle.load(f)
      with open(cylinder_vi_auto_95_fixes_file, 'rb') as f:
        cylinder_auto_fixes_95 = pickle.load(f)
    else:      
      # #
      # # perform merge correction with p < .05
      # #
      # print 'Correcting merge errors with p < .05'
      # bigM_dojo_05, corrected_rhoana_05 = mlp.Legacy.perform_auto_merge_correction(cnn, bigM_dojo, input_image, input_prob, input_rhoana, merge_errors, .05)

      # print '   Mean VI improvement', original_mean_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[0]
      # print '   Median VI improvement', original_median_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[1]

      #
      # perform split correction with p > .95
      #
      print 'Correcting split errors with p > .95'
      bigM_cylinder_05 = bigM_cylinder
      corrected_rhoana_05 = input_rhoana
      bigM_cylinder_after_95, out_cylinder_volume_after_auto_95, cylinder_auto_fixes_95, cylinder_auto_vi_s_95 = mlp.Legacy.splits_global_from_M_automatic(cnn, bigM_cylinder_05, input_image, input_prob, corrected_rhoana_05, input_gold, sureness_threshold=.95)

      cylinder_vi_95 = mlp.Legacy.VI(input_gold, out_cylinder_volume_after_auto_95)

      with open(cylinder_vi_95_file, 'wb') as f:
        pickle.dump(cylinder_vi_95, f)

      with open(cylinder_vi_auto_95_fixes_file, 'wb') as f:
        pickle.dump(cylinder_auto_fixes_95, f)

      with open(cylinder_auto_vis_95_file, 'wb') as f:
        pickle.dump(cylinder_auto_vi_s_95, f)        

    print '   Mean VI improvement', original_mean_VI-cylinder_vi_95[0]
    print '   Median VI improvement', original_median_VI-cylinder_vi_95[1]





    print
    cylinder_vi_99_file = output_folder + '/cylinder_vi_99.p'
    if os.path.exists(cylinder_vi_99_file):
      print 'Loading merge errors p < .01 and split errors p > .99 from file..'
      with open(cylinder_vi_99_file, 'rb') as f:
        cylinder_vi_99 = pickle.load(f)
    else:      
      # #
      # # perform merge correction with p < .01
      # #
      # print 'Correcting merge errors with p < .01'
      # bigM_dojo_05, corrected_rhoana_05 = mlp.Legacy.perform_auto_merge_correction(cnn, bigM_dojo, input_image, input_prob, input_rhoana, merge_errors, .05)

      # print '   Mean VI improvement', original_mean_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[0]
      # print '   Median VI improvement', original_median_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[1]

      #
      # perform split correction with p > .99
      #
      print 'Correcting split errors with p > .99'
      bigM_cylinder_01 = bigM_cylinder
      corrected_rhoana_01 = input_rhoana
      bigM_cylinder_after_99, out_cylinder_volume_after_auto_99, cylinder_auto_fixes_99, cylinder_auto_vi_s_99 = mlp.Legacy.splits_global_from_M_automatic(cnn, bigM_cylinder_01, input_image, input_prob, corrected_rhoana_01, input_gold, sureness_threshold=.99)

      cylinder_vi_99 = mlp.Legacy.VI(input_gold, out_cylinder_volume_after_auto_99)

      with open(cylinder_vi_99_file, 'wb') as f:
        pickle.dump(cylinder_vi_99, f)

    print '   Mean VI improvement', original_mean_VI-cylinder_vi_99[0]
    print '   Median VI improvement', original_median_VI-cylinder_vi_99[1]


    print
    cylinder_vi_0_file = output_folder + '/cylinder_vi_0.p'
    cylinder_vi_auto_0_fixes_file = output_folder + '/cylinder_vi_0_fixes.p'
    cylinder_auto_vis_0_file = output_folder + '/cylinder_auto_vis_0.p'    
    if os.path.exists(cylinder_vi_0_file):
      print 'Loading split errors p >= .0 from file..'
      with open(cylinder_vi_0_file, 'rb') as f:
        cylinder_vi_0 = pickle.load(f)
      with open(cylinder_vi_auto_0_fixes_file, 'rb') as f:
        cylinder_auto_fixes_00 = pickle.load(f)
      with open(cylinder_auto_vis_0_file, 'rb') as f:
        cylinder_auto_vi_s_00 = pickle.load(f)


    else:      
      # #
      # # perform merge correction with p < .01
      # #
      # print 'Correcting merge errors with p < .01'
      # bigM_dojo_05, corrected_rhoana_05 = mlp.Legacy.perform_auto_merge_correction(cnn, bigM_dojo, input_image, input_prob, input_rhoana, merge_errors, .05)

      # print '   Mean VI improvement', original_mean_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[0]
      # print '   Median VI improvement', original_median_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_05)[1]

      #
      # perform split correction with p > .99
      #
      print 'Correcting split errors with p >= .0'
      bigM_cylinder_00 = bigM_cylinder
      corrected_rhoana_00 = input_rhoana
      bigM_cylinder_after_00, out_cylinder_volume_after_auto_00, cylinder_auto_fixes_00, cylinder_auto_vi_s_00 = mlp.Legacy.splits_global_from_M_automatic(cnn, bigM_cylinder_00, input_image, input_prob, corrected_rhoana_00, input_gold, sureness_threshold=.0)

      cylinder_vi_0 = mlp.Legacy.VI(input_gold, out_cylinder_volume_after_auto_00)

      with open(cylinder_vi_0_file, 'wb') as f:
        pickle.dump(cylinder_vi_0, f)

      with open(cylinder_vi_auto_0_fixes_file, 'wb') as f:
        pickle.dump(cylinder_auto_fixes_00, f)

      with open(cylinder_auto_vis_0_file, 'wb') as f:
        pickle.dump(cylinder_auto_vi_s_00, f)      

    print '   Mean VI improvement', original_mean_VI-cylinder_vi_0[0]
    print '   Median VI improvement', original_median_VI-cylinder_vi_0[1]



    print
    cylinder_vi_simuser_file = output_folder + '/cylinder_vi_simuser.p'
    cylinder_fixes_simuser_file = output_folder + '/cylinder_fixes_simuser.p'
    cylinder_vis_simuser_file = output_folder + '/cylinder_vi_s_simuser.p'
    if os.path.exists(cylinder_vi_simuser_file):
      print 'Loading merge errors and split errors (simulated user) from file..'
      with open(cylinder_vi_simuser_file, 'rb') as f:
        cylinder_vi_simuser = pickle.load(f)
      with open(cylinder_fixes_simuser_file, 'rb') as f:
        cylinder_sim_user_fixes = pickle.load(f)
      with open(cylinder_vis_simuser_file, 'rb') as f:
        cylinder_sim_user_vi_s = pickle.load(f)


    else:
      # #
      # # perform merge correction with simulated user
      # #
      # print 'Correcting merge errors by simulated user (er=0)'
      # bigM_dojo_simuser, corrected_rhoana_sim_user, sim_user_fixes = mlp.Legacy.perform_sim_user_merge_correction(cnn, bigM_dojo, input_image, input_prob, input_rhoana, input_gold, merge_errors)
      
      # print '   Mean VI improvement', original_mean_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_sim_user)[0]    
      # print '   Median VI improvement', original_median_VI-mlp.Legacy.VI(input_gold, corrected_rhoana_sim_user)[1]
      
      #
      # perform split correction with simulated user
      #
      print 'Correcting split errors by simulated user (er=0)'
      bigM_cylinder_simuser = bigM_cylinder
      corrected_rhoana_sim_user = input_rhoana
      bigM_cylinder_after, out_cylinder_volume_after_sim_user, cylinder_sim_user_fixes, cylinder_sim_user_vi_s = mlp.Legacy.splits_global_from_M(cnn, bigM_cylinder_simuser, input_image, input_prob, corrected_rhoana_sim_user, input_gold, hours=-1)

      cylinder_vi_simuser = mlp.Legacy.VI(input_gold, out_cylinder_volume_after_sim_user)

      with open(cylinder_vi_simuser_file, 'wb') as f:
        pickle.dump(cylinder_vi_simuser, f)      

      with open(cylinder_vis_simuser_file, 'wb') as f:
        pickle.dump(cylinder_sim_user_vi_s, f)

      with open(cylinder_fixes_simuser_file, 'wb') as f:
        pickle.dump(cylinder_sim_user_fixes, f)

    print '   Mean VI improvement', original_mean_VI-cylinder_vi_simuser[0]
    print '   Median VI improvement', original_median_VI-cylinder_vi_simuser[1]


    data = collections.OrderedDict()
    data['Automatic\nSegmentation'] = mlp.Legacy.VI(input_gold, input_rhoana)[2]
    data['Simulated   \nUser   '] = cylinder_vi_simuser[2]
    data['Automatic\nCorrections\n(p=.95)'] = cylinder_vi_95[2]
    data['Automatic\nCorrections\n(p=.99)'] = cylinder_vi_99[2]


    mlp.Legacy.plot_vis(data, output_folder+'/cylinder_vi.pdf')

    #
    # Simple VI boxplot
    #
    data = collections.OrderedDict()
    data['Initial\nSegmentation'] = mlp.Legacy.VI(input_gold, input_rhoana)[2]
    data['Automatic\nCorrections'] = cylinder_vi_95[2]    
    data['Guided\n(Simulated)'] = cylinder_vi_simuser[2]

    mlp.Legacy.plot_vis(data, output_folder+'/cylinder_vi_simple.pdf')




    proofread_vis = [original_VI_s] + cylinder_sim_user_vi_s
    vi_s_per_correction = [np.median(proofread_vis[0])]
    for m in proofread_vis[1:]:
        for i in range(30*12):
            vi_s_per_correction.append(np.median(m))

    mlp.Legacy.plot_vi_simuser(vi_s_per_correction, output_folder+'/cylinder_simuser_vi.pdf')

    proofread_vis_auto = [original_VI_s] + cylinder_auto_vi_s_00
    vi_s_per_correction_auto = [np.median(proofread_vis_auto[0])]
    for m in proofread_vis_auto[1:]:
        for i in range(30*12):
            vi_s_per_correction_auto.append(np.median(m))

    # mlp.Legacy.plot_vi_combined(vi_s_per_correction_auto, vi_s_per_correction, output_folder+'/cylinder_combined_vi.pdf')

    mlp.Legacy.plot_vi_combined_no_interpolation(vi_s_per_correction_auto, vi_s_per_correction, output_folder+'/cylinder_combined_vi_no_interpolation.pdf', sweetspot=len(cylinder_auto_fixes_95))


    data = {}
    y_text_fixes = [v[0] for v in cylinder_sim_user_fixes]
    y_pred_fixes = [v[1] for v in cylinder_sim_user_fixes]
    fpr, tpr, _ = roc_curve(y_text_fixes, y_pred_fixes)
    roc_auc = auc(fpr, tpr)    
    data['Cylinder Fixes'] = (fpr, tpr, roc_auc)
    mlp.Legacy.plot_roc(data, output_folder+'/cylinder_roc.pdf')

