import os, shutil, time
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
print('ROOT', root)
models = ['decision_tree_model.pkl','logistic_regression_model.pkl','random_forest_model.pkl','support_vector_machine_model.pkl']
for m in models:
    src = os.path.join(root, m)
    dst = os.path.join(root, 'models', m)
    if os.path.exists(src):
        shutil.move(src, dst)
        print('MOVED', src, '->', dst)
    else:
        print('MISSING', src)

bkdir = os.path.join(root, 'archive', 'backups')
if not os.path.exists(bkdir):
    os.makedirs(bkdir)

for fn in ['upi.db','upi_fraud_dataset.csv']:
    src = os.path.join(root, fn)
    if os.path.exists(src):
        ts = time.strftime('%Y%m%d_%H%M%S')
        dst = os.path.join(bkdir, f"{fn}.{ts}")
        shutil.copy2(src, dst)
        print('COPIED', src, '->', dst)
        # delete original
        os.remove(src)
        print('REMOVED ORIGINAL', src)
    else:
        print('MISSING', src)

print('\nMODELS/ CONTENTS:')
for f in os.listdir(os.path.join(root, 'models')):
    print(' -', f)

print('\nARCHIVE/BACKUPS CONTENTS:')
for f in os.listdir(bkdir):
    print(' -', f)
