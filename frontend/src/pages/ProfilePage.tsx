import React from 'react';
import { ArrowUpRight, CalendarDays, Mail, ShieldCheck, UserRound } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export const ProfilePage: React.FC = () => {
  const { user } = useAuth();

  return (
    <section className="workspace-page profile-page">
      <div className="workspace-heading">
        <div>
          <span className="eyebrow">YOUR SPACE, YOURS ALONE</span>
          <h1>Profile</h1>
          <p>Your personal details and workspace account information.</p>
        </div>
      </div>
      <div className="profile-card">
        <div className="profile-card-top">
          <div className="profile-avatar">
            {user?.avatar ? (
              <img src={user.avatar} alt={user.name} />
            ) : user?.name ? (
              user.name.charAt(0).toUpperCase()
            ) : (
              'C'
            )}
          </div>
          <div>
            <h2>{user?.name || 'SAP Consultant'}</h2>
            <span>Connected enterprise profile</span>
          </div>
        </div>
        <div className="profile-field">
          <span>
            <UserRound size={15} /> Full name
          </span>
          <strong>{user?.name || 'Not provided'}</strong>
        </div>
        <div className="profile-field">
          <span>
            <Mail size={15} /> Email address
          </span>
          <strong>{user?.email || 'Not provided'}</strong>
        </div>
        {user?.dateOfBirth && (
          <div className="profile-field">
            <span>
              <CalendarDays size={15} /> Date of birth
            </span>
            <strong>{user.dateOfBirth}</strong>
          </div>
        )}
        <div className="profile-field">
          <span>
            <ShieldCheck size={15} /> Security Model
          </span>
          <strong>
            JWT Enterprise Isolation <ArrowUpRight size={13} />
          </strong>
        </div>
      </div>
    </section>
  );
};
