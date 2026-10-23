insert into public.pos_tags(tag,english,dutch,description_zh,example,sort_order,app_pos,app_pos_label_zh,app_pos_label_en,display_order,is_content_pos)
values('PREFIX','prefix','voorvoegsel','构词前缀或复合词的前置构词成分','rasmuzikant; recordomzet',90,'prefix','构词前缀','prefix',90,false)
on conflict(tag) do nothing;
