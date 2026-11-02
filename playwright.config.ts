import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'tests/ui',use:{baseURL:process.env.STOCK_MONITOR_TEST_URL||'http://127.0.0.1:1420',viewport:{width:1380,height:980},headless:true},reporter:'list'});
