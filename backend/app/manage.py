"""Local account administration; passwords are read interactively, never CLI flags."""
import argparse,getpass,sqlite3
from . import db,local_identity as identity

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['create-user','reset-password','set-role','disable-user','enable-user'])
    parser.add_argument('--username',required=True)
    parser.add_argument('--role',choices=list(identity.ROLES))
    parser.add_argument('--must-change-password',action='store_true')
    args=parser.parse_args()
    if args.command in ('create-user','reset-password'):
        password=getpass.getpass('Password: ')
        if password!=getpass.getpass('Confirm password: '):raise SystemExit('Passwords do not match')
    if args.command=='set-role' and not args.role:parser.error('set-role requires --role')
    db.init(recover=False);identity.init()
    try:
        if args.command=='create-user':identity.create_user(args.username,password,args.role or 'super_admin',args.must_change_password)
        else:
            with db.connect() as c:
                user=c.execute('SELECT id FROM local_user WHERE username=?',(args.username,)).fetchone()
                if not user:raise identity.LocalError('USER_NOT_FOUND','User not found')
                if args.command=='reset-password':c.execute('UPDATE local_user SET password_hash=?,must_change=1,version=version+1 WHERE id=?',(identity.password_hash(password),user['id']))
                elif args.command=='set-role':c.execute('UPDATE local_user SET role=?,version=version+1 WHERE id=?',(args.role,user['id']))
                else:c.execute('UPDATE local_user SET status=?,version=version+1 WHERE id=?',('disabled' if args.command=='disable-user' else 'active',user['id']))
                c.execute('DELETE FROM local_session WHERE owner=?',(user['id'],))
    except (identity.LocalError,sqlite3.IntegrityError):raise SystemExit('User creation failed: check username, role and password policy') from None
    print('Local user command completed: '+args.command+' '+args.username)
if __name__=='__main__':main()
