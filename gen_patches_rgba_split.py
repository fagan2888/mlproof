import cPickle as pickle
import mahotas as mh
import numpy as np
import os
import time
import sys

import mlproof as mlp

PATCH_PATH = os.path.expanduser('~/patches/cylinder1_rgba/')



def generate_patches(start_slice, end_slice, filename):

    patch_index = 0

    all_patches_count = 0
    patch_list = []
    all_error_patches = []
    all_correct_patches = []
    
    for z in range(start_slice, end_slice):

        t0 = time.time()
        print 'working on slice', z
        input_image, input_prob, input_mask, input_gold, input_rhoana = mlp.Util.read_section(os.path.expanduser('~/data/cylinder/'),z)

        error_patches, patches = mlp.Patch.patchify_maxoverlap(input_image, input_prob, input_mask, input_rhoana, input_gold, sample_rate=1)

#         for e in patches:
#             if e['image'].max() == 0.:
#                 print 'ZERRRRO', z
        
        print 'Generated', len(error_patches), 'split error patches and', len(patches), ' correct patches in', time.time()-t0, 'seconds.'
        
        patch_list.append(patches)
        all_error_patches += error_patches
        all_correct_patches += patches
        
    
    
    NO_PATCHES = len(all_error_patches) + len(all_correct_patches)

    print 'We have a total of',NO_PATCHES,'patches.'
    print 'Errors:',len(all_error_patches)
    print 'Correct:',len(all_correct_patches)    
    
    with open(PATCH_PATH+'/'+filename+'_'+str(start_slice)+'_'+str(end_slice)+'_error_patches.p', 'wb') as f:
        pickle.dump(all_error_patches, f)

    with open(PATCH_PATH+'/'+filename+'_'+str(start_slice)+'_'+str(end_slice)+'_correct_patches.p', 'wb') as f:
        pickle.dump(all_correct_patches, f)

    return None


    PATCH_BYTES = 75*75
    P_SIZE = (NO_PATCHES, 4, 75,75) # rather than raveled right now
    
    p_rgba = np.zeros(P_SIZE, dtype=np.float32)
    p_rgba_large = np.zeros(P_SIZE, dtype=np.float32)    
    
#     p_image = np.zeros(P_SIZE, dtype=np.float32)
#     p_prob = np.zeros(P_SIZE, dtype=np.float32)
#     p_binary = np.zeros(P_SIZE, dtype=np.bool)
#     p_merged_array = np.zeros(P_SIZE, dtype=np.bool)
# #     p_dyn_obj = np.zeros((NO_PATCHES, PATCH_BYTES),dtype=np.bool)
# #     p_dyn_bnd = np.zeros((NO_PATCHES, PATCH_BYTES),dtype=np.bool)
#     p_border_overlap = np.zeros(P_SIZE, dtype=np.bool)
#     p_larger_border_overlap = np.zeros(P_SIZE, dtype=np.bool)    
    p_target = np.zeros(NO_PATCHES)


    i = 0
    for p in all_error_patches:

        p_rgba[i][0] = p['image']
        p_rgba[i][1] = p['prob'] 
        p_rgba[i][2] = p['merged_array']
        p_rgba[i][3] = p['border_overlap']
        
        p_rgba_large[i][0] = p['image']
        p_rgba_large[i][1] = p['prob']    
        p_rgba_large[i][2] = p['merged_array']
        p_rgba_large[i][3] = p['larger_border_overlap']        
        
        p_target[i] = 1 # <--- important
        i += 1

        
    for p in all_correct_patches:

        p_rgba[i][0] = p['image']
        p_rgba[i][1] = p['prob']    
        p_rgba[i][2] = p['merged_array']
        p_rgba[i][3] = p['border_overlap']
        
        p_rgba_large[i][0] = p['image']
        p_rgba_large[i][1] = p['prob']       
        p_rgba_large[i][2] = p['merged_array']
        p_rgba_large[i][3] = p['larger_border_overlap']        
        
        p_target[i] = 0 # <--- important
        i+=1
        
    
    return p_rgba, p_rgba_large, p_target



def shuffle_in_unison_inplace(a, b, c):
    assert len(a) == len(b)
    p = np.random.permutation(len(a))
    return a[p], b[p], c[p]



def run(start_slice, end_slice, filename):
    
    if not os.path.exists(PATCH_PATH):
        os.makedirs(PATCH_PATH)
    
    p = generate_patches(start_slice, end_slice, filename)
    
    # shuffled = shuffle_in_unison_inplace(p[0],
    #                                      p[1],
    #                                      p[2]
    #                                     )
    
    # print 'saving..'
    # np.savez(PATCH_PATH+filename+'.npz', rgba=shuffled[0],
    #                                      rgba_large=shuffled[1])
    # np.savez(PATCH_PATH+filename+'_targets.npz', targets=shuffled[2])
    # print 'Done!'
    

###
###
###

run(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])

