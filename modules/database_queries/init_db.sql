create database if not exists todo_database;


-- task
    -- name: str
    -- description: str
    -- priority: int  # enum type
    -- is_complete: bool

create table if not exists tasks ( -- master table, all tasks live here
    name text,
    description text,
    priority integer,
    is_complete integer,
    meta_data text, -- just in case we need to do some cursed shit? 
)

create table if not exists tasks_complete ( -- tasks that are complete, or ones that have a 1 in the is_complete row
    name text,
    description text,
    priority integer,
    is_complete integer,
    meta_data text, -- just in case we need to do some cursed shit? 

)

create table if not exists tasks_pending ( -- tasks that are complete, or ones that have a 1 in the is_complete row
    name text,
    description text,
    priority integer,
    is_complete integer,
    meta_data text, -- just in case we need to do some cursed shit? 
)



