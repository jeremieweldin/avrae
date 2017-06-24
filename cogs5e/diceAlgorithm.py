import asyncio
import copy
import json
import os
import random
import re
import shlex

import discord
from discord.ext import commands
import numexpr

from cogs5e.funcs.dice import roll, SingleDiceGroup, Constant, Operator
from cogs5e.funcs.lookupFuncs import searchSpell, searchMonster
from cogs5e.funcs.sheetFuncs import sheet_attack
from utils import checks
from utils.functions import fuzzy_search, a_or_an, discord_trim, \
    parse_args_2


class Dice:
    """Dice and math related commands."""
    def __init__(self, bot):
        self.bot = bot
        
    async def on_message(self, message):
        if message.content.startswith('!d20'):
            self.bot.botStats["dice_rolled_session"] += 1
            self.bot.db.incr('dice_rolled_life')
            rollStr = message.content.replace('!', '1').split(' ')[0]
            try:
                rollFor = ' '.join(message.content.split(' ')[1:])
            except:
                rollFor = ''
            adv = 0
            if re.search('(^|\s+)(adv|dis)(\s+|$)', rollFor) is not None:
                adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollFor) is not None else -1
                rollFor = re.sub('(adv|dis)(\s+|$)', '', rollFor)
            out = roll(rollStr, adv=adv, rollFor=rollFor, inline=True)
            out = out.result
            try:
                await self.bot.delete_message(message)
            except:
                pass
            await self.bot.send_message(message.channel, message.author.mention + '  :game_die:\n' + out)
            
    def parse_roll_args(self, args, character):
        user_cvars = character.get('cvars', {})
        return args.replace('SPELL', str(user_cvars.get('SPELL', 'SPELL')).strip('+')).replace('PROF', str(character.get('stats', {}).get('proficiencyBonus', "0")))
            
    @commands.command(name='2', hidden=True, pass_context=True)
    async def quick_roll(self, ctx, *, mod:str='0'):
        """Quickly rolls a d20."""
        self.bot.botStats["dice_rolled_session"] += 1
        self.bot.db.incr('dice_rolled_life')
        rollStr = '1d20+' + mod
        adv = 0
        if re.search('(^|\s+)(adv|dis)(\s+|$)', rollStr) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollStr) is not None else -1
            rollStr = re.sub('(adv|dis)(\s+|$)', '', rollStr)
        out = roll(rollStr, adv=adv, inline=True)
        out = out.result
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say(ctx.message.author.mention + '  :game_die:\n' + out)
                        
        
    @commands.command(pass_context=True, name='roll', aliases=['r'])
    async def rollCmd(self, ctx, *, rollStr:str):
        """Rolls dice in xdy format.
        Usage: !r xdy Attack!
               !r xdy+z adv Attack with Advantage!
               !r xdy-z dis Hide with Heavy Armor!
               !r xdy+xdy*z
               !r XdYkhZ
               !r 4d6mi2[fire] Elemental Adept, Fire
        Supported Operators: k (keep)
                             ro (reroll once)
                             rr (reroll infinitely)
                             mi/ma (min/max result)
                             >/< (test if result is greater than/less than)
        Supported Selectors: lX (lowest X)
                             hX (highest X)"""
        
        adv = 0
        self.bot.botStats["dice_rolled_session"] += 1
        self.bot.db.incr('dice_rolled_life')
        if re.search('(^|\s+)(adv|dis)(\s+|$)', rollStr) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollStr) is not None else -1
            rollStr = re.sub('(adv|dis)(\s+|$)', '', rollStr)
        res = roll(rollStr, adv=adv)
        out = res.result
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        outStr = ctx.message.author.mention + '  :game_die:\n' + out
        if len(outStr) > 1999:
            await self.bot.say(ctx.message.author.mention + '  :game_die:\n[Output truncated due to length]\n**Result:** ' + str(res.plain))
        else:
            await self.bot.say(outStr)
            
    @commands.command(pass_context=True, name='debugroll', aliases=['dr'], hidden=True)
    @checks.is_owner()
    async def debug_roll(self, ctx, *, rollStr:str):
        adv = 0
        self.bot.botStats["dice_rolled_session"] += 1
        self.bot.db.incr('dice_rolled_life')
        if re.search('(^|\s+)(adv|dis)(\s+|$)', rollStr) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollStr) is not None else -1
            rollStr = re.sub('(adv|dis)(\s+|$)', '', rollStr)
        res = roll(rollStr, adv=adv, debug=True)
        out = res.result
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        outStr = ctx.message.author.mention + '  :game_die:\n' + out
        if len(outStr) > 1999:
            await self.bot.say(ctx.message.author.mention + '  :game_die:\n[Output truncated due to length]\n**Result:** ' + str(res.plain))
        else:
            await self.bot.say(outStr)
        
        debug = ""
        for p in res.raw_dice.parts:
            if isinstance(p, SingleDiceGroup):
                debug += "SingleDiceGroup:\nnum_dice={0.num_dice}, max_value={0.max_value}, annotation={0.annotation}, operators={0.operators}".format(p) + \
                "\nrolled={}\n\n".format(', '.join(repr(r) for r in p.rolled))
            elif isinstance(p, Constant):
                debug += "Constant:\nvalue={0.value}, annotation={0.annotation}\n\n".format(p)
            elif isinstance(p, Operator):
                debug += "Operator:\nop={0.op}, annotation={0.annotation}\n\n".format(p)
            else:
                debug += "Comment:\ncomment={0.comment}\n\n".format(p)
        for t in discord_trim(debug):
            await self.bot.say(t)
    
    @commands.command(pass_context=True, name='multiroll', aliases=['rr'])
    async def rr(self, ctx, iterations:int, rollStr, *, args=''):
        """Rolls dice in xdy format a given number of times.
        Usage: !rrr <iterations> <xdy> [args]"""
        if iterations < 1 or iterations > 500:
            return await self.bot.say("Too many or too few iterations.")
        self.bot.botStats["dice_rolled_session"] += iterations
        self.bot.db.incr('dice_rolled_life')
        adv = 0
        out = []
        if re.search('(^|\s+)(adv|dis)(\s+|$)', args) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', args) is not None else -1
            args = re.sub('(adv|dis)(\s+|$)', '', args)
        for _ in range(iterations):
            res = roll(rollStr, adv=adv, rollFor=args, inline=True)
            out.append(res)
        outStr = "Rolling {} iterations...\n".format(iterations)
        outStr += '\n'.join([o.skeleton for o in out])
        if len(outStr) < 1500:
            outStr += '\n{} total.'.format(sum(o.total for o in out))
        else:
            outStr = "Rolling {} iterations...\n[Output truncated due to length]\n".format(iterations) + \
            '{} total.'.format(sum(o.total for o in out))
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say(ctx.message.author.mention + '\n' + outStr)
        
    @commands.command(pass_context=True, name='iterroll', aliases=['rrr'])
    async def rrr(self, ctx, iterations:int, rollStr, dc:int=0, *, args=''):
        """Rolls dice in xdy format, given a set dc.
        Usage: !rrr <iterations> <xdy> <DC> [args]"""
        if iterations < 1 or iterations > 500:
            return await self.bot.say("Too many or too few iterations.")
        self.bot.botStats["dice_rolled_session"] += iterations
        self.bot.db.incr('dice_rolled_life')
        adv = 0
        out = []
        successes = 0
        if re.search('(^|\s+)(adv|dis)(\s+|$)', args) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', args) is not None else -1
            args = re.sub('(adv|dis)(\s+|$)', '', args)
        for r in range(iterations):
            res = roll(rollStr, adv=adv, rollFor=args, inline=True)
            if res.plain >= dc:
                successes += 1
            out.append(res)
        outStr = "Rolling {} iterations, DC {}...\n".format(iterations, dc)
        outStr += '\n'.join([o.skeleton for o in out])
        if len(outStr) < 1500:
            outStr += '\n{} successes.'.format(str(successes))
        else:
            outStr = "Rolling {} iterations, DC {}...\n[Output truncated due to length]\n".format(iterations, dc) + '{} successes.'.format(str(successes))
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say(ctx.message.author.mention + '\n' + outStr)
        
    @commands.command(pass_context=True)
    async def cast(self, ctx, *, args : str):
        """Casts a spell (i.e. rolls all the dice and displays a summary [auto-deleted after 15 sec]).
        Valid Arguments: -r <Some Dice> - Instead of rolling the default dice, rolls this instead."""
        
        try:
            guild_id = ctx.message.server.id 
            pm = self.bot.db.not_json_get("lookup_settings", {}).get(guild_id, {}).get("pm_result", False)
               
        except:
            pm = False
        
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        
        args = args.split('-r')
        args = [re.sub('^\s+|\s+$', '', a) for a in args]
        spellName = args[0]
        
        spell = searchSpell(spellName, return_spell=True)
        self.bot.botStats["spells_looked_up_session"] += 1
        self.bot.db.incr('spells_looked_up_life')
        if spell['spell'] is None:
            return await self.bot.say(spell['string'][0], delete_after=15)
        result = spell['string']
        spell = spell['spell']
        
        if len(args) == 1:
            rolls = spell.get('roll', None)
            if isinstance(rolls, list):
                active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id) # get user's active
                if active_character is not None:
                    user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {}) # grab user's characters
                    character = user_characters[active_character] # get Sheet of character
                    rolls = self.parse_roll_args('\n'.join(rolls), character)
                    rolls = rolls.split('\n')
                out = "**{} casts {}:** ".format(ctx.message.author.mention, spell['name']) + '\n'.join(roll(r, inline=True).skeleton for r in rolls)
            elif rolls is not None:
                active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id) # get user's active
                if active_character is not None:
                    user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {}) # grab user's characters
                    character = user_characters[active_character] # get Sheet of character
                    rolls = self.parse_roll_args(rolls, character)
                out = "**{} casts {}:** ".format(ctx.message.author.mention, spell['name']) + roll(rolls, inline=True).skeleton
            else:
                out = "**{} casts {}!** ".format(ctx.message.author.mention, spell['name'])
        else:
            rolls = args[1:]
            roll_results = ""
            for r in rolls:
                res = roll(r, inline=True)
                if res.total is not None:
                    roll_results += res.result + '\n'
                else:
                    roll_results += "**Effect:** " + r
            out = "**{} casts {}:**\n".format(ctx.message.author.mention, spell['name']) + roll_results
            
        await self.bot.say(out)
        for r in result:
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r, delete_after=15)
                
    @commands.command(pass_context=True, aliases=['ma'])
    async def monster_atk(self, ctx, monster_name, atk_name='list', *, args=''):
        """Rolls a monster's attack.
        Attack name can be "list" for a list of all of the monster's attacks.
        Valid Arguments: adv/dis
                         -ac [target ac]
                         -b [to hit bonus]
                         -d [damage bonus]
                         -d# [applies damage to the first # hits]
                         -rr [times to reroll]
                         -t [target]
                         -phrase [flavor text]
                         crit (automatically crit)"""
        
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        
        monster = searchMonster(monster_name, return_monster=True, visible=True)
        self.bot.botStats["monsters_looked_up_session"] += 1
        self.bot.db.incr('monsters_looked_up_life')
        if monster['monster'] is None:
            return await self.bot.say(monster['string'][0], delete_after=15)
        monster = monster['monster']
        attacks = monster.get('attacks')
        monster_name = a_or_an(monster.get('name'))[0].upper() + a_or_an(monster.get('name'))[1:]
        if atk_name == 'list':
            attacks_string = '\n'.join("**{0}:** +{1} To Hit, {2} damage.".format(a['name'],
                                                                                  a['attackBonus'],
                                                                                  a['damage'] or 'no') for a in attacks)
            return await self.bot.say("{}'s attacks:\n{}".format(monster_name, attacks_string))
        attack = fuzzy_search(attacks, 'name', atk_name)
        if attack is None:
            return await self.bot.say("No attack with that name found.", delete_after=15)
        
        args = shlex.split(args)
        args = parse_args_2(args)
        args['name'] = monster_name
        attack['details'] = attack.get('desc')
        
        result = sheet_attack(attack, args)
        embed = result['embed']
        embed.colour = random.randint(0, 0xffffff)
        
        await self.bot.say(embed=embed)
            
