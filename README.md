# AnnoTinder Python backend

A Python backend for the AnnoTinder client, using FastAPI and SQLAlchemy.

Note that this is in active development, so please don't use it as this point.

# Authentication

## Admin authenticatin

Admins can log in with passwords. These passwords are properly slow hashed and salted, but still, make sure to not re-use important passwords.

## User authentication

AnnoTinder very deliberately doesn't allow regular users to login with password authentication. We want you to be able to easily set up an AnnoTinder server, but if you are responsible for passwords, easy doesn't cut it. Basically, we try to avoid anything that could accidentaly cause you to cause harm.

Instead, there are four ways for users to authenticate:

- **Option 1: They don't**. You can allow users to log in with their current device (i.e. browser). This is not real authentication, because you can never tell whether they are really who they say they are. The only thing that you know is that annotations were made by the same user. (though note that you can include survey questions in a job to ask for )
- **Option 2: Invited ID**.

Users can therefore chose a username, but their user ID is designed so that users that choose the same name

As long as they don't clear the browser data, they can log-in

Admins can use password authentication.

By default, only admins can be

Users can login via magic-links
