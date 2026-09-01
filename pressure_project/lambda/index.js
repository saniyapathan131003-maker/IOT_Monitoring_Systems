const { Client } = require('pg');
const awsIot = require('aws-iot-device-sdk');

const supabaseConfig = {
    host: process.env.SUPABASE_HOST,
    port: process.env.SUPABASE_PORT,
    user: process.env.SUPABASE_USER,
    password: process.env.SUPABASE_PASSWORD,
    database: process.env.SUPABASE_DB
};

// AWS IoT device setup (example)
const device = awsIot.device({
    keyPath: process.env.AWS_IOT_KEY,
    certPath: process.env.AWS_IOT_CERT,
    caPath: process.env.AWS_IOT_CA,
    clientId: 'lambda-node-client',
    host: process.env.AWS_IOT_HOST
});

exports.handler = async (event) => {
    const client = new Client(supabaseConfig);
    try {
        await client.connect();

        // Example: insert incoming IoT data into Supabase
        const { sensor, value } = event;
        await client.query('INSERT INTO sensor_data(sensor, value) VALUES($1, $2)', [sensor, value]);

        await client.end();

        return {
            statusCode: 200,
            body: JSON.stringify({ message: 'Data inserted successfully!' })
        };
    } catch (err) {
        console.error(err);
        return {
            statusCode: 500,
            body: JSON.stringify({ error: err.message })
        };
    }
};
