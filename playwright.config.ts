import {defineConfig} from '@playwright/test';
const executablePath=process.env.STOCK_MONITOR_TEST_BROWSER;
export default defineConfig({testDir:'tests/ui',use:{baseURL:process.env.STOCK_MONITOR_TEST_URL||'http://127.0.0.1:1420',viewport:{width:1380,height:980},headless:true,...(executablePath?{launchOptions:{executablePath}}:{})},reporter:'list'});
